import os
import time
import json
import hashlib
import argparse
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# -----------------------------------------------------------------------------
# Constants
# -----------------------------------------------------------------------------
BASE_URL = "https://wechatmini-6.photoplus.cn"
# The salt is split across three string literals in the JS source (search
# `"eiwu"` / `"lax"` / `"iaoh"` around line 18895 of app_reference.js). Combined
# it is the well-known value below.
SALT = "lax" + "iaoh" + "eiwu"  # "laxiaoheiwu"
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# -----------------------------------------------------------------------------
# Signature
#
# Entry point: lines 18891-18904 / 18953-18967 / 19009-19023:
#
#   _t       = +new Date            // current ms timestamp
#   payload  = Object.assign({}, params, {_t}, extras)
#   C        = X(payload).replace(/"/g, "")   // X is module 3de1 export "E"
#   _s       = md5(C + SALT)                  // 32-char hex
#   query    = {...params, _s, _t}            // strip null/undefined entries
#
# The *critical* piece is the stringifier X (line 15286):
#
#   function X(t) {
#       for (var keys = Object.keys(t).sort(), i = "", s = 0; s < keys.length; s++)
#           if (t[k] != null) {
#               t[k] = JSON.stringify(t[k]);         // per-value stringify
#               i += (i.indexOf("=") != -1 ? "&" : "") + k + "=" + t[k];
#           }
#       return i;
#   }
#
# So: keys are SORTED alphabetically, each value is JSON.stringify'd
# individually (strings keep their quotes, then all `"` are stripped at the
# end), and entries are joined as k1=v1&k2=v2.
# -----------------------------------------------------------------------------
def _stringify_for_sign(payload: dict) -> str:
    """Port of module 3de1 export E (function X)"""
    out = ""
    for k in sorted(payload.keys()):
        v = payload[k]
        if v is None:
            continue
        v_str = json.dumps(v, ensure_ascii=False, separators=(",", ":"))
        out += ("&" if "=" in out else "") + k + "=" + v_str
    return out


def sign_params(params: dict) -> dict:
    t = int(time.time() * 1000)
    payload = {**params, "_t": t}
    sign_str = _stringify_for_sign(payload).replace('"', "")
    s = hashlib.md5((sign_str + SALT).encode("utf-8")).hexdigest()
    signed = {**params, "_s": s, "_t": t}
    # Drop None entries exactly like the JS `Object.keys(w).map(...delete B[t])`.
    # Empty strings are kept on purpose (faceUrl/faceHash/ppSign are sent as "").
    return {k: v for k, v in signed.items() if v is not None}


def _default_headers() -> dict:
    # The backend 1001-rejects requests without a matching Referer -- browsers
    # on live.photoplus.cn set this automatically, we have to do it manually.
    return {
        "User-Agent": USER_AGENT,
        "Referer": "https://live.photoplus.cn/",
        "Accept": "application/json, text/plain, */*",
    }


# -----------------------------------------------------------------------------
# API: /live/detail -> father_activity_list
# -----------------------------------------------------------------------------
def fetch_father_activity_list(activity_no: int, debug: bool = False) -> list:
    params = sign_params({"activityNo": int(activity_no)})
    url = f"{BASE_URL}/live/detail"
    if debug:
        print(f"[detail] GET {url} params={params}")
    resp = requests.get(url, params=params, headers=_default_headers(), timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code", 0) == -1:
        raise RuntimeError(f"/live/detail failed: {data.get('message')}")
    result = data.get("result") or {}
    father_list = result.get("father_activity_list") or []
    # Match the JS filter (see app_reference.js line 44363): drop anything
    # whose activity_no is falsy (None / 0 / empty string).
    activity_nos = [f["activity_no"] for f in father_list if f.get("activity_no")]
    if debug:
        print(f"[detail] father_activity_list ({len(activity_nos)}): {activity_nos}")
    return activity_nos


# -----------------------------------------------------------------------------
# API: /home/pic/self/recognize  (this is what JS names `numberLock`)
# -----------------------------------------------------------------------------
def fetch_recognize(activity_no_list: list, number: str, debug: bool = False) -> dict:
    params = sign_params({
        "list": ",".join(str(x) for x in activity_no_list),
        "number": str(number),
        "faceUrl": "",
        "faceHash": "",
        "ppSign": "",
    })
    url = f"{BASE_URL}/home/pic/self/recognize"
    if debug:
        print(f"[recognize] GET {url} params={params}")
    resp = requests.get(url, params=params, headers=_default_headers(), timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code", 0) == -1:
        raise RuntimeError(f"/home/pic/self/recognize failed: {data.get('message')}")
    return data


# -----------------------------------------------------------------------------
# Download
# -----------------------------------------------------------------------------
def download_image_with_retries(url, image_path, image_name, retries=MAX_RETRIES):
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, stream=True, timeout=DEFAULT_TIMEOUT)
            response.raise_for_status()
            with open(os.path.join(image_path, image_name), "wb") as out_file:
                out_file.write(response.content)
            return True, None
        except requests.RequestException as err:
            if attempt < retries:
                time.sleep(2)
            else:
                return False, f"Failed to download {url} after {retries} retries: {err}"
    return False, "Unknown error"


def download_pics(pics_array, folder_name):
    image_path = "./" + str(folder_name)
    if not os.path.exists(image_path):
        os.makedirs(image_path)

    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = []
        downloaded = 0
        errors = []
        for pic in pics_array:
            origin = pic.get("origin_img") or ""
            if not origin:
                continue
            image_url = "https:" + origin if origin.startswith("//") else origin
            image_name = pic.get("pic_name", "unknown.jpg")
            image_size = pic.get("show_size", 0)
            try:
                exif_timestamp = str(pic["relate_time"]).split(" ")[1].replace(":", "")
            except Exception:
                exif_timestamp = "000000"

            target_name = exif_timestamp + "_" + image_name
            target_path = os.path.join(image_path, target_name)

            if os.path.exists(target_path):
                if os.path.getsize(target_path) == image_size:
                    downloaded += 1
                    continue
                # file exists but size differs -> save as _1 suffix
                alt_name = exif_timestamp + "_" + image_name[:-4] + "_1.JPG"
                futures.append(executor.submit(download_image_with_retries, image_url, image_path, alt_name))
                print(
                    f"File {image_name} already exists, but size is different. "
                    f"Existing: {os.path.getsize(target_path)}, New: {image_size}"
                )
            else:
                futures.append(executor.submit(download_image_with_retries, image_url, image_path, target_name))

        with tqdm(total=len(futures), desc="Downloading Images", unit="file") as pbar:
            for future in as_completed(futures):
                success, error = future.result()
                if success:
                    downloaded += 1
                else:
                    errors.append(error)
                pbar.update(1)

    if errors:
        print("Some errors occurred during downloads:")
        for err in errors:
            print(err)

    return downloaded


# -----------------------------------------------------------------------------
# Entry
# -----------------------------------------------------------------------------
def run(activity_no: int, number: str, folder_name: str = None, debug: bool = False):
    folder = folder_name if folder_name else str(number)
    image_path = "./" + str(folder)
    if not os.path.exists(image_path):
        os.makedirs(image_path)

    # Step 1: get child activity_no list from /live/detail
    activity_no_list = fetch_father_activity_list(activity_no, debug=debug)
    if not activity_no_list:
        # Fall back to the activity the user asked about.
        activity_no_list = [int(activity_no)]
        print(f"[warn] father_activity_list is empty, falling back to [{activity_no}]")

    # Step 2: call /home/pic/self/recognize with number + activity list
    res_json = fetch_recognize(activity_no_list, number, debug=debug)

    # Persist the raw response for debugging.
    with open(image_path + "_recognize.json", "w", encoding="utf-8") as f:
        json.dump(res_json, f, ensure_ascii=False, indent=4)

    result = res_json.get("result") or {}
    pics_array = result.get("pics_array") or []
    total_pics = result.get("pics_total", len(pics_array))
    camer = pics_array[0]["camer"] if pics_array else "Unknown"

    print(f"Total Photos: {total_pics} - Activities: {len(activity_no_list)} - Photographer: {camer}")

    if not pics_array:
        print("No pictures returned for this number.")
        return True

    downloaded = download_pics(pics_array, folder)
    print(f"Downloaded: {downloaded}/{total_pics}")
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download images from photoplus by activityNo + number (using live-time signing)."
    )
    parser.add_argument("--activityNo", type=int, required=True, help="top-level activity number")
    parser.add_argument("--number", type=str, required=True, help="bib / racer number to search for")
    parser.add_argument(
        "--folder_name",
        type=str,
        default=None,
        help="output folder name (defaults to the --number value)",
    )
    parser.add_argument("--debug", action="store_true", help="print request debug info")
    args = parser.parse_args()

    run(args.activityNo, args.number, args.folder_name, debug=args.debug)

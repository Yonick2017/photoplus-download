
import os
import time
import requests
import hashlib
from operator import itemgetter
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import json
import argparse

MAX_RETRIES = 3

# 下载图片
def download_image_with_retries(url, image_path, image_name, retries=MAX_RETRIES):
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()  # 如果响应状态不是200，就主动抛出异常
            with open(os.path.join(image_path, image_name), 'wb') as out_file:
                out_file.write(response.content)
            return True, None  # 下载成功
        except requests.RequestException as err:
            if attempt < retries:
                time.sleep(2)  # 等待 2 秒后重试
            else:
                return False, f"Failed to download {url} after {retries} retries: {err}"
    return False, "Unknown error"  # 理论上不会到这一步

def get_all_images(url, folder_name):
    image_path = "./" + str(folder_name)
    if not os.path.exists(image_path):
        os.makedirs(image_path)
    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()  # 如果响应状态不是200，就主动抛出异常
    except requests.RequestException as err:
        print(f"Failed to download {url}: {err}")
        return False
    try:
        res_json = response.json()
    except ValueError:
        print("Response content is not valid JSON")
        return False

    total_pics = res_json['result']['pics_total']
    pics_array = res_json['result']['pics_array']
    camer = res_json['result']['pics_array'][0]['camer'] if pics_array else "Unknown"
    # save res_json to a file
    with open(image_path + f"_original.json", "w", encoding="utf-8") as f:
        json.dump(res_json, f, ensure_ascii=False, indent=4)

    # 开始多线程下载，带进度条
    with ThreadPoolExecutor(max_workers=32) as executor:
        futures = []
        downloaded = 0
        errors = []
        for pic in pics_array:
            image_url = "https:" + pic['origin_img']
            image_name = pic['pic_name']
            image_size = pic['show_size']
            try:
                exif_timestamp = str(pic['relate_time']).split(' ')[1].replace(":", "")
            except:
                exif_timestamp = "000000"
            # check if already downloaded
            if os.path.exists(os.path.join(image_path, exif_timestamp + '_' + image_name)):
                # check if the file size is same
                if os.path.getsize(os.path.join(image_path, exif_timestamp + '_' + image_name)) == image_size:
                    downloaded += 1
                    continue

                futures.append(
                    executor.submit(download_image_with_retries, image_url, image_path, exif_timestamp + '_' + image_name[:-4] + "_1.JPG")
                )
                print(f"File {image_name} already exists, but size is different. Existing size: {os.path.getsize(os.path.join(image_path, exif_timestamp + '_' + image_name))}, New size: {image_size}")
            else:
                futures.append(
                    executor.submit(download_image_with_retries, image_url, image_path, exif_timestamp + '_' + image_name)
                )

        with tqdm(total=len(futures), desc="Downloading Images", unit="file") as pbar:
            for future in as_completed(futures):
                success, error = future.result()
                if success:
                    downloaded += 1
                else:
                    errors.append(error)
                pbar.update(1)

    print(
        f"Total Photos: {total_pics} - Downloaded: {downloaded} - Photographer: {camer}"
    )

    if errors:
        print("Some errors occurred during downloads:")
        for err in errors:
            print(err)
    
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Download images from photoplus link.')
    parser.add_argument('--url', type=str, required=True, help='photoplus link')
    parser.add_argument('--folder_name', type=str, required=True, help='image path')
    args = parser.parse_args()
    get_all_images(args.url, args.folder_name)


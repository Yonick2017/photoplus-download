import os
import time
import requests
import hashlib
from operator import itemgetter
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import json
import argparse

# 常量
SALT = 'laxiaoheiwu'
COUNT = 9999
MAX_RETRIES = 3

# 定义请求的参数
data = {
    'activityNo': 0,
    'isNew': False,
    'count': COUNT,
    'page': 1,
    'ppSign': 'live',
    'picUpIndex': '',
    '_t': 0,
}

# 对象按键排序
def obj_key_sort(obj):
    sorted_obj = sorted(obj.items(), key=itemgetter(0))
    sorted_obj_dict = {k: str(v) for k, v in sorted_obj if v is not None}
    return '&'.join([f"{k}={v}" for k, v in sorted_obj_dict.items()])

# MD5加密
def md5(value):
    m = hashlib.md5()
    m.update(value.encode('utf-8'))
    return m.hexdigest()

# 下载图片
def download_image(url, image_path, image_name):
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()  # 如果响应状态不是200，就主动抛出异常
    except requests.RequestException as err:
        print(f"Failed to download {url}: {err}")
        return False
    with open(os.path.join(image_path, image_name), 'wb') as out_file:
        out_file.write(response.content)
    return True

def download_image_with_retries(url, image_path, image_name, retries=MAX_RETRIES):
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, stream=True)
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


# 获取所有图片
def get_all_images(id, place):
    image_path = "./" + str(place)
    if not os.path.exists(image_path):
        os.makedirs(image_path)
    t = int(time.time() * 1000)
    data['activityNo'] = id
    data['_t'] = t
    data_sort = obj_key_sort(data)
    sign = md5(data_sort + SALT)
    params = {
        **data,
        '_s': sign,
        'ppSign': 'live',
        'picUpIndex': '',
    }

    if READ_LOCAL_JSON and os.path.exists(image_path + f"res_{count_start}to{count_end}.json"):
        with open(image_path + f"res_{count_start}to{count_end}.json", "r", encoding="utf-8") as f:
            res_json = eval(f.read().replace('true', 'True').replace('false', 'False').replace('null', 'None'))

    # if not, send request to get json file
    else:
        try:
            # res = requests.get('https://live.photoplus.cn/pic/pics', params=params)
            header = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3',
                'Cookie': 'vip_year_type=1; can_see=1; home_guide=true; wx_login=false; activity_no=21348644; activity_url=https://open.weixin.qq.com/connect/oauth2/authorize?appid=wxe89488e21d961fe0&redirect_uri=https%3A%2F%2Flive.photoplus.cn%2Factivity%2Flive%2F21348644%3FuniqCode%3D%26activityNo%3D21348644%26userType%3Dnull&response_type=code&scope=snsapi_userinfo&state=STATE#wechat_redirect=; Hm_lvt_6b7a1b5481a225f36fb2f2a25107192c=1732449090,1732802737; Hm_lpvt_6b7a1b5481a225f36fb2f2a25107192c=1732802737; HMACCOUNT=07E8F613A7D6496C',
            }

            res = requests.get('https://wechatmini-6.photoplus.cn/pic/pics', params=params, headers=header)
            res.raise_for_status()  # 如果响应状态不是200，就主动抛出异常
        except requests.RequestException as err:
            print("Oops: Something Else Happened", err)
            return
        try:
            res_json = res.json()
        except ValueError:
            print("Response content is not valid JSON")
            return

    total_pics = res_json['result']['pics_total']
    pics_array = res_json['result']['pics_array']
    camer = res_json['result']['pics_array'][0]['camer'] if pics_array else "Unknown"
    pageTotal = int(res_json['result']['pageTotal'])
    # save res_json to a file
    with open(image_path + f"res_{count_start}to{count_end}.json", "w", encoding="utf-8") as f:
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

    # Save all links to a txt file
    if SAVE_LINKS:
        with open(os.path.join(image_path, f"links_{count_start}to{count_end}.txt"), "w", encoding="utf-8") as f:
            for pic in pics_array:
                f.write("https:" + pic["origin_img"] + "\n")
        print("All links saved to links.txt")

    if errors:
        print("Some errors occurred during downloads:")
        for err in errors:
            print(err)
    
    return pageTotal

# -----------------------------------------------------------------------------------

# Parse command line arguments
parser = argparse.ArgumentParser(description='Download images from photoplus.')
parser.add_argument('--save-links', action='store_true', help='Save image links to a file')
parser.add_argument('--read-local-json', action='store_true', help='Read from local JSON file if available')
parser.add_argument('--download-continuous', action='store_true', help='Download images continuously')
parser.add_argument('--activity-loc-date', type=str, required=True, help='Activity location and date')
parser.add_argument('--activity-name', type=str, required=True, help='Activity name')
parser.add_argument('--id', type=str, required=True, help='Activity ID')
parser.add_argument('--total-pics', type=int, required=True, help='Total number of pictures')
parser.add_argument('--start-page', type=int, default=1, help='Start page for downloading images')

args = parser.parse_args()

SAVE_LINKS = args.save_links
READ_LOCAL_JSON = args.read_local_json
DOWNLOAD_CONTINUOUS = args.download_continuous
activityLocDate = args.activity_loc_date
activityName = args.activity_name
id = args.id
totalPics = args.total_pics
start_page = args.start_page

# -----------------------------------------------------------------------------------


count = "5000"
place = activityLocDate + "_" + activityName + "_" + id + "_" + str(totalPics)
data['page'] = start_page
max_workers_setting = 24

if count.isnumeric():
    data['count'] = int(count)

count_start = data['count'] * (data['page'] - 1) + 1
count_end = data['count'] * data['page']
pageTotal = -1

if id.isnumeric():
    pageTotal = get_all_images(int(id), place)
    if DOWNLOAD_CONTINUOUS:
        while pageTotal > data['page']:
            data['page'] += 1
            count_start = data['count'] * (data['page'] - 1) + 1
            count_end = data['count'] * data['page']
            get_all_images(int(id), place)
else:
    print('Wrong ID')

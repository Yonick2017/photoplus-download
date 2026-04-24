import requests
import re
import argparse
import os
import time

def handleTxtFile(txt_file):
    image_urls_original = []
    with open(txt_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        for line in lines:
            # Split the line using '.jpghttp://' as delimiter
            if '.jpghttps://' in line:
                parts = line.split('.jpghttps://')
                for i, part in enumerate(parts):
                    if i == 0:
                        # First part ends with .jpg
                        if part.strip():
                            image_urls_original.append(part.strip() + '.jpg')
                    if i == len(parts) - 1:
                        if part.strip():
                            image_urls_original.append('https://' + part.strip())
                    else:
                        # Subsequent parts start with http://
                        if part.strip():
                            image_urls_original.append('https://' + part.strip() + '.jpg')
            else:
                # If no delimiter found, treat as single URL
                if line.strip():
                    image_urls_original.append(line.strip())
    
    return image_urls_original

def transform_image_urls_to_download_urls(image_urls_original):
    download_urls = []
    for url in image_urls_original:
        # Check if it's an exblog.jp detail URL
        if 'exblog.jp/iv/detail/' in url:
            # Extract the image path from the 'i' parameter
            match = re.search(r'[?&]i=([^&]+)', url)
            if match:
                image_path = match.group(1)
                # URL decode the path (replace %2F with /)
                image_path = image_path.replace('%2F', '/')
                # Construct the download URL
                download_url = f"https://pds.exblog.jp/pds/1/{image_path}"
                download_urls.append(download_url)
            else:
                # If no 'i' parameter found, keep original URL
                download_urls.append(url)
        else:
            # If not an exblog detail URL, keep original URL
            download_urls.append(url)
    
    return download_urls

def download_image_with_retries(url, image_path, image_name, retries=3):
    for attempt in range(1, retries + 1):
        try:
            response = requests.get(url, stream=True, timeout=30)
            response.raise_for_status()  # 如果响应状态不是200，就主动抛出异常
            with open(os.path.join(image_path, image_name), 'wb') as out_file:
                out_file.write(response.content)
            return True, None  # 下载成功
        except requests.RequestException as err:
            if attempt < retries:
                print(f"Failed to download {url} on attempt {attempt}/{retries}. Retrying...")
                time.sleep(2)  # 等待 2 秒后重试
            else:
                return False, f"Failed to download {url} after {retries} retries: {err}"
    return False, "Unknown error"  # 理论上不会到这一步

def extract_date_from_url(url):
    return url.split('/')[-4] + url.split('/')[-3]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Handle txt file.')
    parser.add_argument('--txt_file', type=str, required=False, default='exblog.txt', help='txt file')
    args = parser.parse_args()
    image_urls_original = handleTxtFile(args.txt_file)
    download_urls = transform_image_urls_to_download_urls(image_urls_original)
    download_urls = list(set(download_urls))
    if not os.path.exists(os.path.splitext(os.path.basename(args.txt_file))[0]):
        os.makedirs(os.path.splitext(os.path.basename(args.txt_file))[0])
    print(f"Downloading {len(download_urls)} images")
    for download_url in download_urls:
        success, error = download_image_with_retries(download_url, os.path.splitext(os.path.basename(args.txt_file))[0], extract_date_from_url(download_url) + '_' + download_url.split('/')[-1])
        if success:
            print(f"Downloaded {download_url}")
        else:
            print(f"Failed to download {download_url}: {error}")
            

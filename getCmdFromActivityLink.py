# python .\getCmdFromActivityLink.py --prefix="photoplus_250331_0007.exe" --suffix="--download-continuous" --url="https://wechatmini-6.photoplus.cn/live/detail?activityNo=1897700&_s=1c3b88b8a16003c6473dc353d0e19029&_t=1748052944995"     

import requests
import argparse

def get_cmd_from_activity_link(url, prefix, suffix):
    response = requests.get(url)
    response.raise_for_status()  # Raise exception for non-200 status codes
    data = response.json()
    if data['code'] == -1:
        print(data['message'])
        return
    else:
        date = str(data['result']['start_date']).replace('.', '')
        # city = str(data['result']['city']).replace('-', '')
        city = str(data['result']['father_activity_name']).split(' ')[0]
        
        father_activity_list = data['result']['father_activity_list']
        for father_activity in father_activity_list:
            total_pics = father_activity['pic_count']
            id = father_activity['activity_no']
            activity_name = father_activity['name']
            print(f"{prefix} --activity-loc-date {date}{city} --total-pics {total_pics} --id {id} --activity-name {activity_name} {suffix}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='get commands for download images from photoplus link. An example would be python .\getCmdFromActivityLink.py --prefix="photoplus_250331_0007.exe" --suffix="--download-continuous" --url="')
    parser.add_argument('--url', type=str, required=True, help='activity link')
    parser.add_argument('--prefix', type=str, default='', help='command prefix')
    parser.add_argument('--suffix', type=str, default='', help='command suffix')
    args = parser.parse_args()
    get_cmd_from_activity_link(args.url, args.prefix, args.suffix)

    

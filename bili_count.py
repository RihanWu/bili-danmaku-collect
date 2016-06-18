# -*- coding: utf-8 -*-
"""
Created on Fri Jun 10 12:44:36 2016

@author: Rihan
"""

from gevent import monkey
monkey.patch_all()
import gevent
import gevent.pool
from bili_single import start_with_redo
import requests
import json
import time


cate = "ent-life"

def fetch_roomid(cate, page, room_list):
    headers = {"Accept": "application/json, text/javascript, */*; q=0.01",
               "Accept-Encoding": "gzip, deflate, sdch",
               "Connection": "keep-alive"}
    # Retry max 5 times
    for i in range(5):
        try:
            print("Fetching page", page)
            response = requests.get("http://live.bilibili.com/area/liveList?area="+ cate +"&order=online&page=" + str(page),
                                    headers=headers,
                                    stream=True)
            temp = b""
            for chunk in response.iter_content(128):
                temp = b"".join([temp, chunk])
            parse = json.loads(temp.decode("utf-8"))
#            parse = json.loads(response.text)
            for item in parse["data"]:
                room_list.append((item["roomid"], item["title"]))
            return
        except:
            print("Retrying", i, "fetching page", page)
            continue
    print("Too many retry fetching page", page)

def update_room_list(cate):
    if cate == "all":
        count_cate = "hot"
    else:
        count_cate = cate
    print("Start fetching room list")
    room_list = []
    BATCH_NUM = 10
    fetch_pool = gevent.pool.Pool(BATCH_NUM)
    # Get total count and go concurrent
    try:
        for i in range(5):
            try:
                headers = {"Accept": "application/json, text/javascript, */*; q=0.01",
                       "Accept-Encoding": "gzip, deflate, sdch",
                       "Connection": "keep-alive"}
                response = requests.get("http://live.bilibili.com/index/refresh?area=" + count_cate,
                                        headers=headers)
                parse = json.loads(response.text)
                count = parse["data"]["count"]
                print("Get count", count)
                print("Using normal method")
                pages_needed = int(count/32) + 1
                fetch_pool.map(lambda a:fetch_roomid(*a),
                               [(cate, j+1, room_list) for j in range(pages_needed)])
                return list(set(room_list))
            except:
                print("Retrying fetch room count")
                continue
        raise Exception
    # Fall back to loop method
    except:
        for i in range(5):
            try:
                print("Fallback to loop method")
                trial = 0
                while True:
                    len_before = len(room_list)
                    for i in range(trial*BATCH_NUM, (trial+1)*BATCH_NUM):
                        print("Trying ten pages")
                        fetch_pool.spawn(fetch_roomid, cate, i + 1, room_list)
                    fetch_pool.join()
                    if len(room_list)-len_before < 320:
                        break
                    trial += 1
                return list(set(room_list))
            except:
                print("Retrying fetch room count")
                continue
        raise Exception("Can't get room data")


try:
    test_list = update_room_list(cate)
    print("room count:{}".format(len(test_list)))

    pool = gevent.pool.Pool()
    start_count_time = time.time()

    BATCH_NUM = 20

    for i in range(int(len(test_list)/BATCH_NUM)):
        print("Connecting to rooms")
        for j in test_list[BATCH_NUM*i: BATCH_NUM*(i+1)]:
            pool.spawn(start_with_redo, j[0], 1, j[1], start_count_time)
            print("Spawning ", j[0])
        gevent.sleep(BATCH_NUM * 1)
    print("All started")
    pool.join()
    pool.kill()
    print("Finally")
except KeyboardInterrupt:
    pool.kill()
    print("Kill all")

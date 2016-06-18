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
from time import time
from sys import argv


PRINT_LV = 0

# Dictoinary of {roomid: roomname}
new_dict = {}
# Dictionary of {roomid: (roomname, greenlet)}
current_dict = {}
working_pool = gevent.pool.Pool()


def fetch_roomid(cate, page, room_dict):
    """Get the rooms in one page"""
    
    headers = {"Accept": "application/json, text/javascript, */*; q=0.01",
               "Accept-Encoding": "gzip, deflate, sdch",
               "Connection": "keep-alive"}
    # Retry max 5 times
    for i in range(5):
        try:
            print("Fetching page", page)
            response = requests.get("http://live.bilibili.com/area/liveList?area="+ cate +"&order=online&page=" + str(page),
                                    headers=headers,
                                    stream=True,
                                    timeout = 2)
            temp = b""
            for chunk in response.iter_content(128):
                temp = b"".join([temp, chunk])
            parse = json.loads(temp.decode("utf-8"))
#            parse = json.loads(response.text)
            for item in parse["data"]:
                room_dict[item["roomid"]] = item["title"]
            return
        except:
            print("Retrying", i, "fetching page", page)
            continue
    print("Too many retry fetching page", page)


def update_room_dict(cate):
    """Get room set in a category"""
    
    if cate == "all":
        count_cate = "hot"
    else:
        count_cate = cate
    print("Start fetching room list")
    room_dict = {}
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
                                        headers=headers,
                                        timeout = 2)
                parse = json.loads(response.text)
                count = parse["data"]["count"]
                print("Get count", count)
                print("Using normal method")
                pages_needed = int(count/32) + 1
                fetch_pool.map(lambda a:fetch_roomid(*a),
                               [(cate, j+1, room_dict) for j in range(pages_needed)])
                return room_dict
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
                    len_before = len(room_dict)
                    for i in range(trial*BATCH_NUM, (trial+1)*BATCH_NUM):
                        print("Trying ten pages")
                        fetch_pool.spawn(fetch_roomid, cate, i + 1, room_dict)
                    fetch_pool.join()
                    if len(room_dict)-len_before < 320:
                        break
                    trial += 1
                return room_dict
            except:
                print("Retrying fetch room count")
                continue
        raise Exception("Can't get room data")


def check_ended():
    global new_dict
    global current_dict
    global working_pool
    
    print("Check ended greenlets")
    for key, value in dict(current_dict).items():
        if value[1] not in working_pool.greenlets:
            del current_dict[key]


def add_new(BATCH_NUM, total_count_time, start_count_time):
    global new_dict
    global current_dict
    global working_pool
    
    print("Add new greenlets")
    new_list = list(set(new_dict.keys()) - set(current_dict.keys()))
    for i in range(int(len(new_list)/BATCH_NUM)):
        if PRINT_LV:print("Connecting to rooms")
        for j in new_list[BATCH_NUM*i: BATCH_NUM*(i+1)]:
            new_greenlet = working_pool.spawn(start_with_redo,
                                              j,
                                              1,
                                              new_dict[j],
                                              total_count_time,
                                              start_count_time)
            current_dict[j] = (new_dict[j], new_greenlet)
            if PRINT_LV:print("Spawning ", j)
        gevent.sleep(BATCH_NUM * 1)


def remove_old():
    global new_dict
    global current_dict
    global working_pool
    
    print("Remove old greenlets")
    closed_list = list(set(current_dict.keys()) - set(new_dict.keys()))
    for i in closed_list:
        working_pool.killone(current_dict[i][1])
        del current_dict[i]
        print("Closed room", i)


def update_roomname(total_count_time, start_count_time):
    global new_dict
    global current_dict
    global working_pool
    
    print("Update roomname(start new greenlets)")
    common_list = list(set(current_dict.keys() & set(new_dict.keys())))
    for i in common_list:
        # Name change
        if new_dict[i] != current_dict[i][0]:
            print("NEW:{} OLD:{}".format(new_dict[i], current_dict[i][0]))
            working_pool.killone(current_dict[i][1])
            new_greenlet = working_pool.spawn(start_with_redo,
                                              i,
                                              1,
                                              new_dict[i],
                                              total_count_time,
                                              start_count_time)
            current_dict[i] = (new_dict[i], new_greenlet)
            print("Update room", i)
            gevent.sleep(0)


def job_manager(cate, total_count_time):
    global new_dict
    global current_dict
    global working_pool
    
    BATCH_NUM = 20
    start_count_time = time()
    
    try:
        while (time() - start_count_time < total_count_time):
            try:
                # Contain (roomid, roomname, )
                new_dict = update_room_dict(cate)
                print("Server room count:", len(new_dict))

                gevent.joinall([gevent.spawn(check_ended),
                                gevent.spawn(add_new,
                                             BATCH_NUM,
                                             total_count_time,
                                             start_count_time),
                                gevent.spawn(remove_old),
                                gevent.spawn(update_roomname,
                                             total_count_time,
                                             start_count_time)])
                print("End one loop")
            except KeyboardInterrupt:
                print("KeyboardInterrupt: Kill all")
                break
            except Exception as e:
                print(repr(e))
                continue
            finally:
                # Check every minute
                gevent.sleep(60)
    finally:
        working_pool.kill()
        current_dict.clear()
        print("Done")


if __name__ == "__main__":
    job_manager(argv[1], int(argv[2]))
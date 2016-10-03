# -*- coding: utf-8 -*-
"""
Created on Fri Jun 10 12:44:36 2016

@author: Rihan
"""

from gevent import monkey
monkey.patch_all()
import gevent
import gevent.pool
from bili_single import start
import requests
import json
from time import time
from sys import argv
from sys import exc_info


PRINT_LV = 0
# roomid is interger
# Dictoinary of {roomid: roomname}
new_dict_async = gevent.event.AsyncResult()
# Dictionary of {roomid: (roomname_async, greenlet)}
current_dict = {}

new_dict_fetching = gevent.event.AsyncResult()
new_dict_fetching.set(False)

#Initial value
new_dict_async.set(dict())
new_dict_ready = gevent.event.AsyncResult()
new_dict_ready.set(False)

# AsyncResult containing current rooms
current_rooms_async = gevent.event.AsyncResult()
working_pool = gevent.pool.Pool()


def fetch_roomid(cate, page, new_dict_async):
    """Get the rooms in one page"""

    headers = {"Accept": "application/json, text/javascript, */*; q=0.01",
               "Accept-Encoding": "gzip, deflate, sdch",
               "Connection": "keep-alive"}
    # Retry max 5 times
    local_dict = {}
    if PRINT_LV:print("Fetching page", page)
    response = requests.get("http://live.bilibili.com/area/liveList?area="+ cate +"&order=online&page=" + str(page),
                            headers=headers,
                            timeout = 2)
    parse = json.loads(response.text)
    for item in parse["data"]:
        local_dict[int(item["roomid"])] = item["title"]
    local_dict.update(new_dict_async.get())
    new_dict_async.set(local_dict)


def update_room_dict(cate, new_dict_async):
    """Get room set in a category"""

    if cate == "all":
        count_cate = "hot"
    else:
        count_cate = cate
    print("Start fetching room list")
    new_dict_fetching.set(True)
    new_dict_async.set(dict())
    # Get total count and go concurrent
    for i in range(3):
        try:
            headers = {"Accept": "application/json, text/javascript, */*; q=0.01",
                   "Accept-Encoding": "gzip, deflate, sdch",
                   "Connection": "keep-alive"}
            response = requests.get("http://live.bilibili.com/index/refresh?area=" + count_cate,
                                    headers=headers,
                                    timeout = 2)
            parse = json.loads(response.text)
            count = parse["data"]["count"]
            if PRINT_LV:print("Get count", count)
            pages_needed = int(count/32) + 1
            g_list = []
            for i in range(pages_needed):
                g_list.append(gevent.spawn_later(0.01*i, fetch_roomid, cate, i+1, new_dict_async))
            gevent.joinall(g_list)
            new_dict_fetching.set(False)
            new_dict_ready.set(True)
            break
        except Exception as e:
            print("Fetch fail because of {}".format(repr(e)))
            print("Retrying fetch room count")
            continue


def check_ended():
    global current_dict
    global working_pool

    count = 0
    for key, value in dict(current_dict).items():
        if value[1] not in working_pool.greenlets:
            del current_dict[key]
            count += 1
    return count


def add_new(BATCH_NUM, end_time):
    global new_dict_async
    global current_dict
    global working_pool
    global current_rooms_async

    new_list = list(set(new_dict_async.get().keys()) - set(current_dict.keys()))
    stat = (len(current_dict), len(new_dict_async.get()), len(new_list))
    current_rooms_async.set(list(new_dict_async.get().keys()))
    for index, roomid in enumerate(new_list):
        if PRINT_LV:print("Connecting to rooms")
        roomname_async = gevent.event.AsyncResult()
        roomname_async.set(new_dict_async.get()[roomid])
        new_greenlet = gevent.spawn_later(index * 0.01,
                                          start,
                                          roomid,
                                          roomname_async,
                                          end_time,
                                          current_rooms_async)
        working_pool.add(new_greenlet)
        current_dict[roomid] = (roomname_async, new_greenlet)
        if PRINT_LV:
            print("Spawning ", roomid)
    return stat


def update_roomname(end_time):
    global new_dict_async
    global current_dict
    global working_pool

    count = 0
    common_list = list(set(current_dict.keys() & set(new_dict_async.get().keys())))
    for i in common_list:
        # Name change
        if new_dict_async.get()[i] != current_dict[i][0].get():
            print("Update roomname {} | OLD:{} | NEW:{}".format(i,
                                                        new_dict_async.get()[i],
                                                        current_dict[i][0].get()))
            current_dict[i][0].set(new_dict_async.get()[i])
            count += 1
    return count


def job_manager(cate, total_count_time):
    global new_dict_async
    global current_dict
    global working_pool

    BATCH_NUM = 20
    end_time = time() + total_count_time
    print_template = "{} ended | {} updated |{} in current_dict | {} in new_dict | {} newly start"

    try:
        while (time() < end_time):
            # Contain (roomid, roomname, )
            if new_dict_ready.get():
                ended_count = check_ended()
                stat = add_new(BATCH_NUM, end_time)
                update_count = update_roomname(end_time)
                print(print_template.format(ended_count,
                                            update_count,
                                            *stat))
                new_dict_ready.set(False)
                gevent.sleep(30)

            if not new_dict_fetching.get():
                gevent.spawn(update_room_dict, cate, new_dict_async)

            gevent.sleep(5)
            if PRINT_LV:
                print("Current pool size {}".format(len(working_pool.greenlets)))
    except KeyboardInterrupt:
        print("KeyboardInterrupt: Kill all")
    except Exception as e:
        print(repr(e))
        exc_type, exc_obj, exc_tb = exc_info()
        print(exc_tb.tb_lineno)
    finally:
        working_pool.kill()
        current_dict.clear()
        print("Done")


if __name__ == "__main__":
    job_manager(argv[1], int(argv[2]))

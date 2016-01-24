"""
for each group, create a list of tuples
mostly singletons, but lectures will be [(lecture1, lecture2, lecture3)]

activities are stored like:
((subject, group), day, starting time in blocks after 8am, block length)

timetables are stored as a list of lists, with either None or a (subject, group) for elements
timetable[5 (days)][24 (blocks of 30 minutes from 8am to 8pm)]

"""

import requests
import json
import itertools
import sys
from functools import reduce
from pprint import pprint
from flask import Flask, render_template
app = Flask(__name__)

API_URL = "https://allocate.timetable.monash.edu/aplus-2016/rest/student/"
HOMEPAGE_URL = "https://allocate.timetable.monash.edu/aplus-2016/student/"
DAY_TO_INDEX_DICT = {
    "Mon": 0,
    "Tue": 1,
    "Wed": 2,
    "Thu": 3,
    "Fri": 4
}


class AllocatePlus:
    def __init__(self, session, data):
        self.session = session
        self.data = data

        self.groups = [] # (subject, group, is_by_start_time)
        for subject in self.data["student"]["student_enrolment"]:
            subject_data = self.data["student"]["student_enrolment"][subject]
            for group in subject_data["groups"]:
                group_data = subject_data["groups"][group]
                status = group_data["status"]
                if status == "ALLOCATION ADJUSTMENT":
                    pass
                elif status == "PREFERENCE ENTRY BY ACTIVITY":
                    self.groups.append((subject, group, False))
                elif status == "PREFERENCE ENTRY BY START TIME":
                    self.groups.append((subject, group, True))
                elif status == "READ ONLY":
                    continue
                elif status == "OFF":
                    continue
                else:
                    print("Unknown status for subject {}, group {}: {}".format(subject, group, status))

        self.all_acts = {} # (subject, group): {repeat: {part: json}}
        # turns into: (subject, group): [[json, json], [json, json], [json, json]]
        # disregard popularity for now
        for subject, group, is_by_start_time in self.groups:
            print("Grabbing activities for", subject, group)
            url = self.get_api_url("{student[student_code]}/subject/{subject}/group/{group}/activities/", subject=subject, group=group)
            activities = self.session.get(url).json()
            g_dict = {}
            
            for activity in activities:
                activity_data = activities[activity]
                act_code = activity_data["activity_code"].split("-")

                repeat = int(act_code[0])
                if repeat not in g_dict:
                    g_dict[repeat] = {}
                if len(act_code) == 2:
                    part = int(act_code[1].lstrip("P"))
                else:
                    part = 1
                g_dict[repeat][part] = activity_data

            for repeat in g_dict:
                g_dict[repeat] = listify(g_dict[repeat])

            self.all_acts[(subject, group)] = listify(g_dict)


        self.unique_times = []
        for key in self.all_acts:
            times = set()
            for repeat in self.all_acts[key]:
                parts = tuple(sorted((key,
                                      day_to_index(d["day_of_week"]),
                                      time_to_blocks(d["start_time"]),
                                      duration_to_blocks(d["duration"])) for d in repeat))
                times.add(parts)
            self.unique_times.append(times)

    def update_data(self):
        self.data = self.session.get(self.get_api_url("{student[student_code]}/")).json()

    def get_api_url(self, url, *args, **kwargs):
        return API_URL + url.format(*args, **kwargs, **self.data)

    @classmethod
    def login(cls, username, password):
        s = requests.Session()
        login = s.post(API_URL + "login", data={"username": username, "password": password})
        s.params.update({"ss": login.json()["token"]})
        homepage = s.get(HOMEPAGE_URL)
        data = json.loads(homepage.text.rsplit("\n", maxsplit=4)[1].lstrip("data=").rstrip(";"))
        return cls(s, data)


def flatten(ttuple):
    # tuple of tuples -> flattened tuple
    return tuple(a for b in ttuple for a in b)

def listify(d):
    # {1: "a", 3: "c", 2: "b"} -> ["a", "b", "c"]
    out = []
    for index in sorted(d.keys()):
        out.append(d[index])
    return out

def day_to_index(day):
    return DAY_TO_INDEX_DICT[day]

def time_to_blocks(time):
    hour, minute = map(int, time.split(":"))
    if minute == 0:
        return 2 * (hour - 8)
    elif minute == 30:
        return 2 * (hour - 8) + 1
    else:
        print("Time isn't a multiple of 30?!?!?!", time)
        return 2 * (hour - 8) + round(minute / 30)

def duration_to_blocks(dur):
    return int(dur) // 30


def get_permutations(unique_times):
    for ttuple in itertools.product(*unique_times):
        classes = flatten(ttuple)
        timetable = [[None for i in range(24)] for j in range(5)]
        for activity, day, time, duration in classes:
            for i in range(duration):
                if timetable[day][time + i] is not None:
                    break
                timetable[day][time + i] = activity
            else:
                continue
            break
        else:
            yield timetable

def score(timetable):
    # Number of days spent on campus
    days_spent = sum(map(any, timetable))
    # Variance of day lengths
    var = variance(list(filter(None, (sum(map(bool, day)) for day in timetable))))
    # Length of days
    day_start_end = [] # [(start, end)]
    breaks = []
    for day in timetable:
        start = None
        end = None
        cur_break = 0
        for i in range(24):
            if day[i]:
                if start is None:
                    start = i
                end = i
                if cur_break:
                    breaks.append(cur_break)
                    cur_break = 0
            else:
                if start:
                    cur_break += 1
        if start is not None and end is not None:
            day_start_end.append((start, end))

    break_squared = sum(x*x for x in breaks)
    total_day_lengths = sum(b-a for a, b in day_start_end)
    day_starts = sum(a for a, b in day_start_end)

    return (-days_spent, -var, -total_day_lengths, day_starts, break_squared)

def variance(l):
    n = 0
    s = 0
    s_sq = 0
    for x in l:
        n += 1
        s += x
        s_sq += x*x
    return (s_sq - (s * s) / n) / n

@app.route("/")
@app.route("/<int:index>")
def show_timetable(index=0):
    global perms
    return render_template("timetable.html", timetable=perms[index], index=index, score=score(perms[index]))

if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("usage:", sys.argv[0], "<Monash username> <Monash password>")
        sys.exit()
    ap = AllocatePlus.login(*sys.argv[1:])
    print("Getting all", reduce(int.__mul__, map(len, ap.unique_times)), "timetable permutations")
    perms = list(get_permutations(ap.unique_times))
    print("Sorting all", len(perms), "permutations with no clashes")
    perms.sort(key=score, reverse=True)
    app.run()

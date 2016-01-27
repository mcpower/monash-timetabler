#! /usr/bin/env python3
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
import os.path
from functools import reduce
from pprint import pprint
from flask import Flask, render_template
from sorting import score, average
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
    def __init__(self, session, data, all_acts=None):
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
        if all_acts is not None:
            self.all_acts = all_acts
        else:
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
    def login(cls, username, password, all_acts=None):
        s = requests.Session()
        login = s.post(API_URL + "login", data={"username": username, "password": password})
        s.params.update({"ss": login.json()["token"]})
        homepage = s.get(HOMEPAGE_URL)
        data = json.loads(homepage.text.rsplit("\n", maxsplit=4)[1].lstrip("data=").rstrip(";"))
        return cls(s, data, all_acts)


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

def create_palette(unique_times):
    subjects = set()
    group_to_options = {} # {group: [number of options]}
    for s in unique_times:
        activity, _, _, _ = next(iter(s))[0]
        subject, group = activity
        subjects.add(subject)
        group_to_options.setdefault(group, []).append(len(s))

    for group in group_to_options:
        group_to_options[group] = average(group_to_options[group])

    subject_hues = {subject: round(i * 360 / len(subjects)) for i, subject in enumerate(subjects)}
    group_values = {}
    sorted_groups = []
    # lectures/noprefs should be pretty dark
    for group in sorted(group_to_options, key=group_to_options.get):
        options = group_to_options[group]
        if options < 1.5:
            group_values[group] = 10
        else:
            sorted_groups.append(group)

    for i, group in enumerate(sorted_groups): # from 25 to 75
        group_values[group] = 25 + round(i * 50 / (len(sorted_groups) - 1))

    return subject_hues, group_values


@app.route("/")
@app.route("/<int:index>")
def show_timetable(index=0):
    global perms, subject_hues, group_values
    return render_template("timetable.html", timetable=perms[index], index=index, score=score(perms[index]), subject_hues=subject_hues, group_values=group_values)


def read_all_acts(s):
    json_all_acts = json.loads(s)
    all_acts = {}
    for key in json_all_acts:
        new_key = tuple(key.split("|"))
        all_acts[new_key] = json_all_acts[key]
    return all_acts


def write_all_acts(all_acts):
    json_all_acts = {}
    for key in all_acts:
        new_key = "|".join(key)
        json_all_acts[new_key] = all_acts[key]
    return json.dumps(json_all_acts)


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print("usage:", sys.argv[0], "<Monash username> <Monash password>")
        sys.exit()
    print("Logging into Allocate+")
    if os.path.isfile("all_acts.json"):
        all_acts = read_all_acts(open("all_acts.json").read())
        ap = AllocatePlus.login(sys.argv[1], sys.argv[2], all_acts)
    else:
        ap = AllocatePlus.login(sys.argv[1], sys.argv[2])
        open("all_acts.json", "w").write(write_all_acts(ap.all_acts))
    print("Getting all", reduce(int.__mul__, map(len, ap.unique_times)), "timetable permutations")
    perms = list(get_permutations(ap.unique_times))
    print("Sorting all", len(perms), "permutations with no clashes")
    perms.sort(key=score, reverse=True)
    print("Generating colour palette")
    subject_hues, group_values = create_palette(ap.unique_times)
    app.run()

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
import re
import urllib.parse
from functools import reduce
from pprint import pprint
from flask import Flask, render_template, Response
from sorting import score, average
app = Flask(__name__)

API_URL = "https://my-timetable.monash.edu/odd/rest/student/"
HOMEPAGE_URL = "https://my-timetable.monash.edu/odd/student"
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
                    self.groups.append((subject, group))
                elif status == "PREFERENCE ENTRY BY START TIME":
                    self.groups.append((subject, group))
                elif status == "READ ONLY":
                    continue
                elif status == "OFF":
                    continue
                else:
                    print("Unknown status for subject {}, group {}: {}".format(subject, group, status))
        self.groups.sort()
        if all_acts is not None:
            self.all_acts = all_acts
        else:
            self.all_acts = {} # (subject, group): {repeat: {part: json}}
            # turns into: (subject, group): [[json, json], [json, json], [json, json]]
            # disregard popularity for now
            for subject, group in self.groups:
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


        self.unique_times = {}
        for key in self.all_acts:
            times = set()
            for repeat in self.all_acts[key]:
                parts = tuple(sorted((day_to_index(d["day_of_week"]),
                                      time_to_blocks(d["start_time"]),
                                      duration_to_blocks(d["duration"])) for d in repeat))
                times.add(parts)
            self.unique_times[key] = sorted(map(list, times))

        self.group_times = [] # zip with self.groups to find how long self.unique_times is
        for group in self.groups:
            self.group_times.append(len(self.unique_times[group]))


    def update_data(self):
        self.data = self.session.get(self.get_api_url("{student[student_code]}/")).json()

    def get_api_url(self, url, *args, **kwargs):
        return API_URL + url.format(*args, **kwargs, **self.data)

    @classmethod
    def login(cls, username, password, all_acts=None):
        s = requests.Session()
        saml_page = s.get(HOMEPAGE_URL)
        login = s.post(saml_page.url, data={
            "UserName": "Monash\\" + username,
            "Password": password,
            "AuthMethod": "FormsAuthentication"
        })
        ss = urllib.parse.parse_qs(urllib.parse.urlparse(login.url).query)["ss"][0]
        s.params.update({"ss": ss})
        data = json.loads(re.search(r"^data=([^;]+);$", login.text, re.M).group(1))
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


def get_permutations(ap):
    for group_indices in itertools.product(*map(range, ap.group_times)):
        activities = [activity for index, group in zip(group_indices, ap.groups) for activity in ap.unique_times[group][index]]
        # activities is list of (day, time, duration) tuples
        activities_per_day = [[] for day in range(5)]
        for day_index, time, duration in activities:
            activities_per_day[day_index].append((time, duration))

        for day in activities_per_day:
            sorted_day = sorted(day)
            if any(day2[0] < day1[0] + day1[1] for day1, day2 in zip(sorted_day, sorted_day[1:])):
                break
        else:
            yield group_indices

def create_timetable(ap, group_indices):
    activities = [(group,) + activity for index, group in zip(group_indices, ap.groups) for activity in ap.unique_times[group][index]]
    timetable = [[None for block in range(24)] for day in range(5)]
    for group, day, time, duration in activities:
        for i in range(duration):
            timetable[day][time + i] = group
    return timetable


def create_palette(ap):
    subjects = set()
    group_to_options = {} # {group: [number of options]}
    for (subject, group), times in zip(ap.groups, ap.group_times):
        subjects.add(subject)
        group_to_options.setdefault(group, []).append(times)

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

@app.route("/perms/<int:start>:<int:end>")
def get_perms(start, end):
    return Response(response=json.dumps(perms[start:end], separators=(",", ":")),
                    status=200,
                    mimetype="application/json")


@app.route("/")
def show_timetable():
    global ap, subject_hues, group_values
    j = json.dumps
    json_unique_times = {"|".join(key): ap.unique_times[key] for key in ap.unique_times}
    return render_template("timetable.html", j=j, subject_hues=subject_hues, group_values=group_values, ap=ap, json_unique_times=json_unique_times)


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
    print("Finding all timetables without clashes from", reduce(int.__mul__, ap.group_times), "timetables")
    perms = list(get_permutations(ap))
    print("Sorting all", len(perms), "permutations")
    perms.sort(key=lambda group_indices: score(create_timetable(ap, group_indices)), reverse=True)
    print("Generating colour palette")
    subject_hues, group_values = create_palette(ap)
    app.run()

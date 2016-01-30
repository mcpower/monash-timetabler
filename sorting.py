"""
This file contains all the logic used for sorting your timetables!
Recommended things to have:
    * basic programming knowledge
    * Python syntax knowledge
    * a decent text editor with syntax highlighting

If you're really clueless, ask a friend with programming knowledge to help you
write a scoring function. When they send you a scoring function, replace
everything from "START SCORING FUNCTION" to "END SCORING FUNCTION" with theirs.

The code should be overly-documented with some examples, so feel free to tinker
around with sorting. I've made examples for most good timetables, so most people
should be fine just by editing my example. If you're in this boat, jump down to
the line which says:
    # START SCORING FUNCTION


Some others would like more control over how they sort their timetables. If
you're one of these people, you should know how timetables are stored in this
script.

Timetables are stored as a list of five days.
Days are stored as a list of 24 blocks of thirty minutes each, from 8am to 8pm.
So day[0] is from 8:00am-8:30am, and day[23] is from 7:30pm-8:00pm.
Blocks are either None, or a tuple of (subject, group) like:
    ("MAT1830_CL_S1_DAY", "Lecture")

So, a timetable is stored as a list of list of maybe tuples. If I were to define
it in a C-like language, I'd define it like this:
    Activity[5][24] timetable;

For most cases, you don't really need to care about WHAT classes are on at what
time, just that you have a class at this time. Thankfully, None is falsy and
activities are truthy, so you can (and should) abuse that fact.

Have fun tinkering!
"""


# START SCORING FUNCTION
def score(timetable):
    """
    The main scoring function.
    Each timetable is given a score based on this function. The highest score
    is the most desirable, and the lowest score is the worst.
    Edit this! I'll lead you through.
    """
    # Useful, precalculated stuff. You probably want to keep this!

    # A list of (day_start, day_end) tuples for each day, and
    # A list of the length of breaks you have.
    startends, breaks = get_startends_and_breaks(timetable)

    # Number of days spent on campus
    days_spent = get_days_spent_on_campus(timetable)

    # A list of the contact hours
    contact_hours = get_contact_hours_per_day(timetable)

    # The variation of your contact hours per day.
    # The lower this is, the more spread out your contact hours are!
    # Minimise this to have a balanced timetable.
    contact_hour_variation = variance(contact_hours)

    # The total sum of how long you're staying at uni
    total_day_lengths = sum(end-start for start, end in startends)

    # The sum of all your break times, squared.
    # The reason why you want to square the breaks is because you'd rather have
    # one 2 hour break than two 1 hour breaks. Maximise this after everything
    # else.
    breaks_squared = sum(breaktime*breaktime for breaktime in breaks)
    
    # The sum of all your starting hours.
    # If you want to sleep in, you probably want to maximise this.
    start_sum = sum(start for start, end in startends)

    # The sum of all your ending hours.
    # Minimise this if you want to get home as early as possible.
    end_sum = sum(end for start, end in startends)


    # Personal preferences.
    # CHANGE THESE!

    # The number of days which start before a specific time.
    # Here, I selected 9:30am as an example. Change this to what suits you.
    days_too_early = num_days_starting_before(startends, time("9:30am"))

    # The number of days which end later than a specific time.
    # I selected 6pm as an example. Change this to what suits you.
    days_too_late = num_days_starting_after(startends, time("6pm"))


    # Some custom scoring!
    """
    This is an example of what you can do with this script.
    I want to get to uni as close to 11am as possible.
    This sums up the difference between day start and 12pm for each day.
    """
    start_time_diff = sum(abs(start - time("12pm")) for start, end in startends)

    """
    A friend of mine has a part time job, so they don't want any classes on
    Wednesday and Thursday.
    The best way to do this is to minimise the number of contact hours on these
    days. Wednesday is timetable[2] and Thursday is timetable[3].
    """
    job_day_contact_hours = get_contact_hours_from_day(timetable[2]) + get_contact_hours_from_day(timetable[3])


    """
    This is where we return, as in, the final part of the function!

    I'd recommend using a tuple, which is (a, collection, of, things) to sort 
    by. It first sorts by the first element (here, the number of days too early 
    for me), then if there are ties, it goes onto the next element, and so on.

    To make it easier to understand, - means that you want to MINIMISE this
    thing (like here, I want to minimise the days too early for me), and + means
    to MAXIMISE this thing (like here, I want to maximise the time my day 
    starts).
    
    The example I'm giving you should be a pretty decent start. Experiment with
    the ordering of the elements and your own scoring!
    """
    return (-days_too_early, -days_too_late, -days_spent, -contact_hour_variation, -total_day_lengths, +start_sum, +breaks_squared)
# END SCORING FUNCTION


"""
After this, we have the helper functions used in the scoring function. You
probably shouldn't edit these, but if you're curious you can see how they work.
"""


def time(time_string):
    """
    Helper function to convert a string to an index.

    String can be any format like:
        9am
        9:30am
        3:30PM
        11:00AM
        13:30
        11 (which is 11am)
        14 (which is 2pm)
    This doesn't support:
        12.5 (why would anyone do this)

    Keep in mind that this represents the block STARTING from the time until 
    30 minutes after. Therefore, the first time block is 8am, and the last is
    7:30pm.
    """
    out = -16 # midnight
    time_string = time_string.lower().strip()
    if time_string.endswith("am"):
        time_string = time_string.rstrip("am").rstrip()
    elif time_string.endswith("pm"):
        time_string = time_string.rstrip("pm").rstrip()
        if not time_string.startswith("12"):
            out += 24

    time_split = [int(x) for x in time_string.split(":")]
    if len(time_split) > 2:
        raise Exception("More than two colons found in time")

    if len(time_split) == 2:
        if time_split[1] == 30:
            out += 1
        elif time_split[1] == 0:
            pass
        else:
            raise Exception("Minutes part of time is not 00 or 30")

    out += time_split[0] * 2

    if 0 <= out <= 24:
        return out
    else:
        raise Exception("Time is outside of the 9am to 7:30pm boundary")


def get_days_spent_on_campus(timetable):
    """
    Returns an integer which is the number of days you spend on campus.
    """
    return sum(map(any, timetable))


def get_contact_hours_per_day(timetable):
    """
    Returns a list of how many 30-minute blocks you have in the timetable.
    For example, my best timetable returns [8, 8, 6, 9, 8].
    This also removes any zeros (free days) it finds in the timetable.

    NOTE: when I say contact hours, I mean number of 30-minute blocks you spend
    in classes/lectures
    """
    return list(filter(None, map(get_contact_hours_from_day, timetable)))


def get_contact_hours_from_day(day):
    """
    Returns the number of contact hours in a day.
    Note that a timetable is a list of days.
    """
    return sum(map(bool, day))


def num_days_starting_before(startends, index):
    """
    Returns an integer, the number of days which have classes before the time.
    For example, if index was 4 (10:00-10:30), it will tell you the number of
    days which have classes between 8am and 10am.
    """
    return sum(start < index for start, end in startends)


def num_days_starting_after(startends, index):
    """
    Returns an integer, the number of days which have classes after the time.
    For example, if index was 20 (18:00-18:30), it will tell you the number of
    days which have classes between 6pm and 8pm.
    """
    return sum(end >= index for start, end in startends)


def get_startends_and_breaks(timetable):
    """
    Returns two things:
        a list of (day_start, day_end) tuples for each day, and
        a list of how long your breaks are, like [4, 8, 2] (a two, four and one
            hour break)
    For example, to find out the total length of your day at uni, subtract
    day_end by day_start.
    """
    startends = [] # [(start, end)]
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
            startends.append((start, end))
    return startends, breaks


def variance(l):
    """
    Returns the variance of a list of numbers.
    Taken from Wikipedia.
    """
    n = 0
    s = 0
    s_sq = 0
    for x in l:
        n += 1
        s += x
        s_sq += x*x
    return (s_sq - (s * s) / n) / n


def average(l):
    """
    Returns the average of a list of numbers.
    Modified from the above code.
    """
    n = 0
    s = 0
    for x in l:
        n += 1
        s += x
    return s / n

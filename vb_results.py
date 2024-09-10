#!/usr/bin/env python3

from flask import Flask
from flask import url_for, render_template, request


import requests
from requests.exceptions import HTTPError
import argparse
import sys, logging
from werkzeug.debug import DebuggedApplication

import datetime

app = Flask(__name__)
app.debug = True
app.wsgi_app = DebuggedApplication(app.wsgi_app, evalex=True)

base_url="https://results.advancedeventsystems.com"

suppress_logging = False
def log(msg, level=logging.INFO):
    if not suppress_logging:
        logging.log(level, msg)


# Formats an ISO-formated timestamp (2023-02-05T11:00:00) to human-friendly (2/5 11:00am)
def format_time(iso):
    if not iso:
        return "Unknown"

    try:
        dt = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S")
        return dt.strftime("%-m/%-d %-I:%M%p")
    except ValueError as e:
        app.logger.warn(f"Unable to parse date '{iso}': {str(e)}")
        return iso


def days_delta_at_midnight(num_days):
    now = datetime.datetime.now()
    dt = now + datetime.timedelta(days = num_days)
    dt = datetime.datetime.combine(dt, datetime.datetime.min.time())
    return f"{dt.isoformat(sep='T', timespec='milliseconds')}%2B00:00"


def match_summary(match_info, play_info, event_id, division_id):
#  play_info {
#       "Type": 0,
#       "PlayId": -57316,
#       "FullName": "Pool 2",
#       "ShortName": "P2",
#       "CompleteShortName": "P2",
#       "CompleteFullName": "Round 1 Pool 2",
#       "Order": 0,
#       "Courts": [
#         {
#           "CourtId": -58868,
#           "Name": "ICC 13",
#           "VideoLink": "https://www.ballertv.com/streams?aes_event_id=28844&aes_court_id=-58868"
#         }
#       ]
#     },
#     match_info:    
#       {
#         "FirstTeamId": 22188,
#         "FirstTeamName": "Elevation 14 Courtney",
#         "FirstTeamWon": false,
#         "FirstTeamText": "Elevation 14 Courtney (OV) (2)",
#         "SecondTeamId": 3821,
#         "SecondTeamName": "NKYVC 14-2 Tide",
#         "SecondTeamWon": false,
#         "SecondTeamText": "NKYVC 14-2 Tide (PR) (18)",
#         "MatchFullName": "Match 1",
#         "MatchShortName": "M1",
#         "HasScores": false,
#         "Sets": [
#           {
#             "FirstTeamScore": null,
#             "SecondTeamScore": null,
#             "ScoreText": "",
#             "IsDecidingSet": false
#           },
#           {
#             "FirstTeamScore": null,
#             "SecondTeamScore": null,
#             "ScoreText": "",
#             "IsDecidingSet": false
#           },
#           {
#             "FirstTeamScore": null,
#             "SecondTeamScore": null,
#             "ScoreText": "",
#             "IsDecidingSet": true
#           }
#         ],
#         "WorkTeamId": 71429,
#         "WorkTeamText": "Circle City 14 Black (HO) (15)",
#         "TypeOfOutcome": 0,
#         "FirstTeamWorkTeamCourtAssignmentFlag": 2,
#         "SecondTeamWorkTeamCourtAssignmentFlag": 0,
#         "MatchId": -57325,
#         "Court": {
#           "CourtId": -58868,
#           "Name": "ICC 13",
#           "VideoLink": "https://www.ballertv.com/streams?aes_event_id=28844&aes_court_id=-58868"
#         },
#         "ScheduledStartDateTime": "2023-01-28T11:00:00",
#         "ScheduledEndDateTime": "2023-01-28T11:59:59"
#       },
    match_model = {
        'event_id':       event_id,
        'division_id':    division_id,
        'play_name':      play_info.get('CompleteFullName', ""),
        'play_id':        play_info.get('PlayId', ""),
        'match_name':     match_info.get('MatchFullName', ""),
        'match_time':     format_time(match_info.get('ScheduledStartDateTime', "")),
        'match_time_raw': match_info.get('ScheduledStartDateTime', ""),
        'court':          match_info.get('Court',{}).get('Name', ""),
        'team_1_name':    match_team_name(match_info, 'First'),
        'team_2_name':    match_team_name(match_info, 'Second'),
        'TeamWorksThisMatch': match_info.get('TeamWorksThisMatch', False)
    }

    if match_info.get('HasScores',None):
        match_model['scores'] = match_scores(match_info)

    return match_model


@app.context_processor
def template_funcs():
    def render_match(match):
        # When building the match model, the 'TeamWorksThisMatch' key is set for matches that the selected team is the work team
        #app.logger.debug(f"render_match: work match {match.get('TeamWorksThisMatch','NOT_THERE')}")
        if match.get('TeamWorksThisMatch'):
            return f"{match.get('match_time','')} | {match.get('play_name','')} | {match.get('match_name','')} | WORK | {match.get('court','')}"

        # Otherwise, render a line with match details
        match_line =  f"{match.get('match_time','')} | {match.get('play_name','')} | {match.get('match_name','')} | {match.get('team_1_name','Team 1')} vs {match.get('team_2_name','Team 2')}"
        if match.get("scores", None):
            return f"{match_line} |  {match.get('scores')}"
        else:
            return f"{match_line} | {match.get('court','')}"
    def render_match_table_row(match):
        event_id = match.get("event_id", "")
        division_id = match.get("division_id", "")
        pool_id = match.get("play_id", "")
        teams = f'{match.get("team_1_name","Team 1")} vs {match.get("team_2_name","Team 2")}'
        if match.get('TeamWorksThisMatch'):
            teams = f'WORK'

        match_line = f'<tr class="match play">'
        match_line = f'{match_line}<td class="match-time">{match.get("match_time","")}</td>'
        match_line = f'{match_line}<td class="pool"><a href="https://results.advancedeventsystems.com/event/{event_id}/divisions/{division_id}/overview/pool/{pool_id}">{match.get("play_name","")}</a></td>'
        match_line = f'{match_line}<td class="match-name">{match.get("match_name","")}</td>'
        match_line = f'{match_line}<td class="teams">{teams}</td>'
        if match.get("scores", None):
            match_line = f'{match_line}<td class="scores">{match.get("scores")}</td>'
        else:
            match_line = f'{match_line}<td class="court"><a href="https://results.advancedeventsystems.com/event/{event_id}/court-schedule">{match.get("court","")}</a></td>'
        match_line = f'{match_line}</tr>'
        return match_line

    return dict(render_match=render_match, render_match_table_row=render_match_table_row)


def match_team_name(match, first_second):
    name_str = f"{match.get(f'{first_second}TeamName', first_second)}"
    if match.get('HasScores',None):
        if match.get(f'{first_second}TeamWon', None):
            name_str = f'(W) {name_str}'
        else:
            name_str = f'(L) {name_str}'
    return name_str


def match_scores(match):
#         "Sets": [
#           {
#             "FirstTeamScore": null,
#             "SecondTeamScore": null,
#             "ScoreText": "",
#             "IsDecidingSet": false
#           },
    scores = []
    for set in match.get('Sets',[]):
        score_1 = set.get("FirstTeamScore","0")
        score_2 = set.get("SecondTeamScore","0")
        if score_1 and score_2:
            scores.append(f'{score_1}-{score_2}')
    return ", ".join(scores)


def json_request(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        if not len(response.content) > 2:
            app.logger.info(f"URL returned no content: {url}")
            return []
        return response.json()
    except HTTPError as http_err:
        app.logger.error(f'HTTP error occurred: {http_err}')
        return {}
    except Exception as err:
        app.logger.error(f'Other error occurred: {err}')
        return {}


def get_event_info(event_id):
# // https://results.advancedeventsystems.com/api/event/{event_id}
# {
#    "Key": "PTAwMDAwMjg4NDU90",
#    "EventId": 28845,
#    "Name": "23 President's Day Classic in St. Louis",
#    "StartDate": "2023-02-18T00:00:00",
#    "EndDate": "2023-02-20T23:59:59.9999999",
#    "Location": "America's Center",
#    "CustomEventType": null,
#    "IsOver": false,

    url = f'{base_url}/api/event/{event_id}'
    json_content = json_request(url)
    event_info = {}
    event_info['event_id'] = json_content.get('Key', "")
    event_info['name'] = json_content.get('Name', "")
    event_info['location'] = json_content.get('Location', "")
    event_info['date'] = json_content.get('StartDate', "").split("T")[0]
    return event_info

def get_team_info(event_id, team_id):
# https://results.advancedeventsystems.com/api/event/{event_id}/teams/{team_id}
# {
#     "TeamId": 169615,
#     "TeamName": "PRV 16U Blue",
#     "TeamCode": "g16prage2pm",
#     "TeamText": "PRV 16U Blue (PM)",
#     "TeamClub": {
#         "ClubId": 11453,
#         "Name": "Palmetto Rage Volleyball Club"
#     },
#     "TeamDivision": {
#         "DivisionId": 137950,
#         "Name": "16 Club",
#         "TeamCount": 40,
#         "CodeAlias": "16C",
#         "ColorHex": "#FF5FFF"
#     },
#     "OpponentTeamId": 171876,
#     "OpponentTeamName": "TEV 16 Carley",
#     "OpponentTeamText": "TEV 16 Carley (SO)",
#     "OpponentClub": {
#         "ClubId": 2747,
#         "Name": "Tri-Cities Extreme"
#     },
#     "NextPendingReseed": false
# }    
    url = f'{base_url}/api/event/{event_id}/teams/{team_id}'
    team_details = json_request(url)
    team_info = {}
    team_info['name'] = team_details.get('TeamName',f'Team {team_id}s')
    team_info['club_name'] = team_details.get('TeamClub',{}).get('Name','')
    team_info['club_id'] = team_details.get('TeamClub',{}).get('ClubId','')
    team_info['division'] = team_details.get('TeamDivision',{}).get('Name','')
    team_info['division_id'] = team_details.get('TeamDivision',{}).get('DivisionId','')
    return team_info


def get_team_schedule(event_id, division_id, team_id, when):
    schedule_funcs = {
        'past': convert_schedule_past,
        'current': convert_schedule_current,
        'future': convert_schedule_future
    }
    match_summaries = schedule_funcs[when](event_id, division_id, team_id)
    if match_summaries is None:
        match_summaries = []
    return match_summaries


# Converts the parsed json representation into a list of match models (dict)
def convert_schedule_current(event_id, division_id, team_id):    
# https://results.advancedeventsystems.com/api/event/{eventId}/division/{divId}/team/{teamId}/schedule/current
# https://results.advancedeventsystems.com/api/event/PTAwMDAwMjg4NDQ90/division/129475/team/3821/schedule/current
# The schedule response is a list of 'plays' (ex: "Pool 2")
# [
#   {
#     "Play": {
#       "Type": 0,
#       "PlayId": -57316,
#       "FullName": "Pool 2",
#       "ShortName": "P2",
#       "CompleteShortName": "P2",
#       "CompleteFullName": "Round 1 Pool 2",
#       "Order": 0,
#       "Courts": [
#         {
#           "CourtId": -58868,
#           "Name": "ICC 13",
#           "VideoLink": "https://www.ballertv.com/streams?aes_event_id=28844&aes_court_id=-58868"
#         }
#       ]
#     },
#     "PlayType": 0,
#     "Matches": [
#       {
#         "FirstTeamId": 22188,
#         "FirstTeamName": "Elevation 14 Courtney",
#         "FirstTeamWon": false,
#         "FirstTeamText": "Elevation 14 Courtney (OV) (2)",
#         "SecondTeamId": 3821,
#         "SecondTeamName": "NKYVC 14-2 Tide",
#         "SecondTeamWon": false,
#         "SecondTeamText": "NKYVC 14-2 Tide (PR) (18)",
#         "MatchFullName": "Match 1",
#         "MatchShortName": "M1",
#         "HasScores": false,
#         "Sets": [
#           {
#             "FirstTeamScore": null,
#             "SecondTeamScore": null,
#             "ScoreText": "",
#             "IsDecidingSet": false
#           },
#           {
#             "FirstTeamScore": null,
#             "SecondTeamScore": null,
#             "ScoreText": "",
#             "IsDecidingSet": false
#           },
#           {
#             "FirstTeamScore": null,
#             "SecondTeamScore": null,
#             "ScoreText": "",
#             "IsDecidingSet": true
#           }
#         ],
#         "WorkTeamId": 71429,
#         "WorkTeamText": "Circle City 14 Black (HO) (15)",
#         "TypeOfOutcome": 0,
#         "FirstTeamWorkTeamCourtAssignmentFlag": 2,
#         "SecondTeamWorkTeamCourtAssignmentFlag": 0,
#         "MatchId": -57325,
#         "Court": {
#           "CourtId": -58868,
#           "Name": "ICC 13",
#           "VideoLink": "https://www.ballertv.com/streams?aes_event_id=28844&aes_court_id=-58868"
#         },
#         "ScheduledStartDateTime": "2023-01-28T11:00:00",
#         "ScheduledEndDateTime": "2023-01-28T11:59:59"
#       },
    url = f'{base_url}/api/event/{event_id}/division/{division_id}/team/{team_id}/schedule/current'
    app.logger.debug(f"Getting current schedule from {url}")
    schedule = json_request(url)
    matches = []
    for play in schedule:
        play_id = play.get('Play', {}).get('PlayId', None)
        if play_id:
            # Get the pool sheet
            url = f'{base_url}/api/event/{event_id}/poolsheet/{play_id}'
            app.logger.debug(f"Getting pool sheet from {url}")
            pool_sheet = json_request(url)
            # { 
            #   "Pool": pool info (same as current schedule pool info, with 'Teams': [...])   
            #   "Matches": [] same structure as current schedule
            #   "FutureRoundMatches": [] similar structure to future schedule
            # }
            play_info = pool_sheet.get('Pool',{})
            
            # Find all of this team's playing matches or working matches
            def is_team_match(m):
                match_teams = [m.get('FirstTeamId',''), m.get('SecondTeamId',''), m.get('WorkTeamId', '')]
                app.logger.debug(f"Checking match team_id={team_id}, teams={match_teams}, match={team_id in match_teams}")
                return team_id in match_teams
            for match in pool_sheet.get('Matches', []):
                if is_team_match(match):
                    # Mark the work matches
                    work_team_id = match.get('WorkTeamId', '')
                    if team_id == work_team_id:
                        #app.logger.debug("!!!!!!!!!!!!! WORK MATCH")
                        match['TeamWorksThisMatch'] = True
                    matches.append(match_summary(match, play_info, event_id, division_id))                   
    return matches


def convert_schedule_past(event_id, division_id, team_id):
    url = f'{base_url}/api/event/{event_id}/division/{division_id}/team/{team_id}/schedule/past'
    app.logger.debug(f"Getting past schedule from {url}")
    schedule = json_request(url)

    matches = []
    #app.logger.info(f'Number of matches: {len(schedule)}', logging.DEBUG)

    # Schedule is: 
    # [ 
    #   {"Match": {...}, "Play": {...}},   
    # ]
    for match_play in schedule:
        play_details = match_play.get('Play',{})
        log(f'Play: {str(play_details)}', logging.DEBUG)
        match_details = match_play.get('Match', {})
        log(f'Match: {str(match_details)}', logging.DEBUG)
        matches.append(match_summary(match_details, play_details, event_id, division_id))
       
    return matches


def convert_schedule_future(event_id, division_id, team_id):
# Schedule is: 
#   {
#       "PotentialRank": 1,
#       "PotentialRankText": "1st-R1 P9 ",
#       "NextMatch": {
#           "MatchId": -50983,
#           "Court": {
#               "CourtId": -51720,
#               "Name": "Court 17",
#               "VideoLink": ""
#           },
#           "ScheduledStartDateTime": "2023-02-05T10:00:00",
#           "ScheduledEndDateTime": "2023-02-05T10:59:59"
#       },
#       "WorkMatch": {
#           "MatchId": -51107,
#           "Court": {
#               "CourtId": -51720,
#               "Name": "Court 17",
#               "VideoLink": ""
#           },
#           "ScheduledStartDateTime": "2023-02-05T11:00:00",
#           "ScheduledEndDateTime": "2023-02-05T11:59:59"
#       },
#       "NextPlay": {
#           "Type": 1,
#           "PlayId": -50979,
#           "FullName": "Challenge Bracket D",
#           "ShortName": "CHBD ",
#           "CompleteShortName": "R2 D1 CHBD ",
#           "CompleteFullName": "Round 2 Division 1 Challenge Bracket D",
#           "Order": 0,
#           "Courts": [
#               {
#                   "CourtId": -51720,
#                   "Name": "Court 17",
#                   "VideoLink": ""
#               }
#           ]
#       },
#       "PlayType": 1,
#       "NextPendingReseed": false
#   },
    # 1ST-R1 P9 -> Round 2 Division 1 Challenge Bracket D | Play: 2/5 10:00am Court 17 | Work: 2/5 11:00am Court 17
    url = f'{base_url}/api/event/{event_id}/division/{division_id}/team/{team_id}/schedule/future'
    app.logger.debug(f"Getting future schedule from {url}")
    schedule = json_request(url)
    matches = []
    for potential_ranking in schedule:
        #app.logger.debug(f"potential_ranking {potential_ranking}")

        next_match = potential_ranking.get('NextMatch',{}) or {}
        #app.logger.debug(f"NextMatch {next_match}")

        next_work = potential_ranking.get('WorkMatch',{}) or {}
        next_play = potential_ranking.get('NextPlay',{}) or {}
        next_court = (next_match.get('Court',{}) or {})
        work_court = (next_work.get('Court',{}) or {})

        match = { 
        'event_id': event_id,
        'rank_text': potential_ranking.get('PotentialRankText', potential_ranking.get('PotentialRank', '')),
        'play_name': next_play.get('CompleteFullName'),
        'play_id': next_play.get('PlayId'),
        'next_match': next_match,
        'next_match_court': next_court.get('Name',''),
        'next_match_time': format_time(next_match.get('ScheduledStartDateTime','')),
        'next_work': next_work,
        #'work_court': next_work.get('Court',{}).get('Name',''),
        'work_time': format_time(next_work.get('ScheduledStartDateTime',''))
        }
        work_court = next_work.get('Court',{})
        if work_court:
            match['work_court']=work_court.get('Name', '')
        matches.append(match)

    return matches

@app.route("/")
def root_page():
    return app.redirect(url_for('event_list'))


@app.route("/events")
def event_list():
# Event listing
# (old) https://results.advancedeventsystems.com/odata/events/scheduler?$orderby=StartDate,Name&$filter=(EndDate+gt+2023-01-23T00:00:00.000Z+and+StartDate+lt+2023-03-01T00:00:00.000Z)
#    url = f"{base_url}/odata/events/scheduler?$orderby=StartDate,Name&$filter=(EndDate+lt+{end_date}+and+StartDate+gt+{start_date})"

# https://advancedeventsystems.com/api/landing/events?$count=true&$filter=(startDate+gt+2023-03-01T04:00:00%2B00:00+and+endDate+le+2023-04-01T04:00:00%2B00:00)&$format=json&$orderby=startDate,name&$top=100
    # TODO: Support date filtering using parameters
    start_date = days_delta_at_midnight(-10)
    end_date = days_delta_at_midnight(40)
    # date format: 2023-03-01T00:00:00.000Z
    url = f"https://advancedeventsystems.com/api/landing/events?$count=true&$filter=(startDate+gt+{start_date}+and+endDate+le+{end_date})&$format=json&$orderby=startDate,name&$top=1000"
    # log(f"Getting events from {url}", logging.ERROR)
    json_content = json_request(url)
    events = json_content.get("value", [])
    # log(f"events: {events}",logging.ERROR)
    output = ["<table><tr><th>Event</th><th>Date</th></tr>"]
    for event in events:
        # log(f"event: {event}",logging.ERROR)
        event_date = event.get("startDate", "").split("T")[0]
        event_id = event.get("eventSchedulerKey",None)
        if event_id:
            output.append(f'<tr><td><a href="{url_for("event_clubs", event_id=event_id)}">{event.get("name","Unknown")}</a></td><td>{event_date}</td></tr>')
    output.append("</table>")
    # return output
    return "\n".join(output)


@app.route("/event/<event_id>")
def event_clubs(event_id):
# Event clubs and divisions (get club id by name)
# https://results.advancedeventsystems.com/api/event/{event_id}
# {
#    "Key": "PTAwMDAwMjg4NDU90",
#    "EventId": 28845,
#    "Name": "23 President's Day Classic in St. Louis",
#    "StartDate": "2023-02-18T00:00:00",
#    "EndDate": "2023-02-20T23:59:59.9999999",
#    "Location": "America's Center",
#    "CustomEventType": null,
#    "IsOver": false,
#    "Clubs": [
#        {
#            "ClubId": 447,
#            "Name": "1st Alliance VBC"
#        },
#     ],
#    "Divisions": [
#        {
#            "IsFinished": false,
#            "DivisionId": 129503,
#            "Name": "11 Girls",
#            "TeamCount": 16,
#            "CodeAlias": "11 Girls",
#            "ColorHex": "#FF7FFF"
#        },
#    ]
#}
    url = f"{base_url}/api/event/{event_id}"
    json_content = json_request(url)
    event_name = json_content.get('Name', "")
    location = json_content.get('Location', "")
    date = json_content.get('StartDate','').split("T")[0]
    output = [f"<h1>{event_name}</h1>"]
    output.append(f"<h2>{date} - {location}</h2>")
    output.append(f"<h3>Clubs</h3>")

    for club in json_content.get('Clubs',[]):
        club_name = club.get('Name','Unknown')
        club_id = club.get('ClubId','')
        club_url = url_for("event_club_teams", event_id=event_id, club_id=club_id)
        output.append(f'<a href="{club_url}">{club_name}</a>')
    return "<br/>".join(output)


@app.route("/event/<event_id>/<club_id>")
def event_club_teams(event_id, club_id):
# Club teams (get division id and team id for club id + team name)
# https://results.advancedeventsystems.com/odata/{event_id}/nextassignments(dId=null,cId={club_id},tIds=[])?$orderby=TeamName,TeamCode
#{
#    "@odata.context": "http://results.advancedeventsystems.com/odata/PTAwMDAwMjg4NDU90/$metadata#NextAssignmentViewModel",
#    "value": [
#        {
#            "TeamId": 3822,
#            "TeamName": "NKYVC 13-1 Tsunami",
#            "TeamCode": "g13nkyvc1pr",
#            "TeamText": "NKYVC 13-1 Tsunami (PR)",
#            "OpponentTeamName": null,
#            "OpponentTeamText": null,
#            "OpponentTeamId": null,
#            "SearchableTeamName": "nkyvc 13-1 tsunami",
#            "NextPendingReseed": false,
#            "NextWorkMatchDate": null,
#            "TeamClub": {
#                "ClubId": 468,
#                "Name": "NKYVC"
#            },
#            "TeamDivision": {
#                "DivisionId": 129507,
#                "Name": "13 Open",
#                "TeamCount": 18,
#                "CodeAlias": "13O",
#                "ColorHex": "#FF7F5F"
#            },
#            "OpponentClub": null,
#            "NextMatch": null,
#            "WorkMatchs": []
#        },
#    ]
# }        
    output = []
    event_info = get_event_info(event_id)
    output.append(f"<h1>{event_info.get('name','')}</h1>")
    output.append(f"<h2>{event_info.get('date','')} - {event_info.get('location','')}</h2>")
    url = f"{base_url}/odata/{event_id}/nextassignments(dId=null,cId={club_id},tIds=[])?$orderby=TeamName,TeamCode"
    json_content = json_request(url)
    club_name = json_content.get('value',[{}])[0].get('TeamClub',{}).get('Name','')
    output.append(f"<h3>{club_name}</h3>")
    teams = json_content.get('value',[])
    for team in teams:
        team_name = team.get('TeamName','Unknown')
        team_id = team.get('TeamId','')
        division = team.get('TeamDivision', {})
        division_name = division.get('Name', 'Unknown')
        division_id = division.get('DivisionId', '')
        team_url = url_for("team_page", event_id=event_id, division_id=division_id, team_id=team_id)
        output.append(f'<a href="{team_url}">{team_name} ({division_name})</a>')
    return "<br/>".join(output)


@app.route("/event/<event_id>/<division_id>/<team_id>")
def team_page(event_id, division_id, team_id):
    args = request.args
    format = args.get('fmt', default="rich")
    model = { 'event_id': event_id, 'division_id': division_id, 'team_id': team_id}
    model['team_info'] = get_team_info(event_id, team_id)
    event_info = get_event_info(event_id)
    model['event_info'] = event_info

    model['past_schedule'] = get_team_schedule(event_id, division_id, team_id, 'past')


    model['current_schedule'] = get_team_schedule(event_id, division_id, team_id, 'current')

    model['future_schedule'] = get_team_schedule(event_id, division_id, team_id, 'future')

    return render_template(f"team_page_{format}.html", **model)

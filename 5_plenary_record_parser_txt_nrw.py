# coding: utf-8
import os
import locale
import re
import logging
import pandas as pd
from datetime import datetime
from tqdm import tqdm

from lib import helper

log = logging.getLogger(__name__)

BUNDESLAND = 'NRW'
DATA_PATH = f"data/{BUNDESLAND}"

locale.setlocale(locale.LC_TIME, "de_DE.utf-8")

# regular expressions to capture speeches of one session
BEGIN_STRING = r'^<poi_begin>Beginn:?\s+(?:[0-9]{1,2}[.:][0-9]{1,2}|[0-9]{1,2})(?:\s+Uhr)?'
END_STRING = r'^(?:Schluss|Ende):?\s+(?:[0-9]{1,2}[.:][0-9]{1,2}|[0-9]{1,2}\s*Uhr)'
CHAIR_STRING = r'^<poi_begin>(Alterspräsident(?:in)?|(?:Geschäftsführender\s+)?Präsident(?:in)?|Erste(?:r)?\s+Vizepräsident(?:in)?|Vizepräsident(?:in)?)\s+(.+)(?:\s+\((?:fortfahrend|unterbrechend)\))?'

# parties
# CDU, SPD, GRÜNE, FDP, PIRATEN, AfD, fraktionslos
SPEAKER_STRING = r'^<poi_begin>(.+)(?:\s+<poi_end>|<poi_end>\s+)?(?:\*\))?\((CDU|SPD|FDP|PIRATEN|GRÜNE|AfD|fraktionslos)'
EXECUTIVE_STRING = r'^<poi_begin>(.+?)(?:<poi_end>,(?:\*\))?\s+|,(?:\*\))?(?:\s+<poi_end>|<poi_end>\s+))(geschäftsführender|Minister(?:in)?\s+(?:für|der|des)\s+(?:.+)|Ministerpräsident(?:in)?|Finanzminis(?:-|ter(?:in)?)|Justizminister(?:in)?)'
OFFICIALS_STRING = r'^<poi_begin>(Staatssekretär(?:in)?)\s+(.+)'

# compilation of regular expressions
# advantage combination of strings is possible
BEGIN_MARK = re.compile(BEGIN_STRING)
END_MARK = re.compile(END_STRING)
CHAIR_MARK = re.compile(CHAIR_STRING)
SPEAKER_MARK = re.compile(SPEAKER_STRING)
EXECUTIVE_MARK = re.compile(EXECUTIVE_STRING)
OFFICIALS_MARK = re.compile(OFFICIALS_STRING)
EXECUTIVE_MARK_SECOND = re.compile(r'^<poi_begin>Ministerpräsident(?:in)?\s+(.+?)<poi_end>')
CONSTITUTIONAL_COURT_MARK = re.compile(r'^<poi_begin>(.+?),<poi_end>\s+Präsident(?:in)?\s+des\s+Verfas-')
INTERJECTION_MARK = re.compile(r'^(?:<poi_begin>)?<interjection_begin>\(')
INTERJECTION_END = re.compile(r'\)$')
DATE_CAPTURE = re.compile(r'([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4})')
POI_ONE_LINER = re.compile(r'^(.+?)?<poi_end>(?:.+)?$')

files = [os.path.join(dp, f) for dp, dn, fn in os.walk(os.path.expanduser(os.path.join(DATA_PATH, "txt"))) for f in fn if f.endswith("xml.txt")]

ls_speeches = []
ls_interjection_length = []
ls_text_length = []

errormessages = []

def append_speech(speeches, current_speaker, current_party, text, seq, sub, current_executive, current_servant, wp, session, current_president, current_role, BUNDESLAND, interjection, date, issue):
    speech = pd.DataFrame({'speaker': [current_speaker],
                        'party': [current_party],
                        'speech': [text],
                        'seq': [seq],
                        'sub': [sub],
                        'executive': current_executive,
                        'servant': current_servant,
                        'wp': wp,
                        'session': session,
                        'president': current_president,
                        'role': [current_role],
                        'state': [BUNDESLAND],
                        'interjection': interjection,
                        'date': [date],
                        'issue': issue})
    speeches.append(speech)

for filename in (pbar := tqdm(files)):
    # extracts wp, session no. and if possible date of plenary session
    numbers = re.search(r"(\d\d)-(\d{1,3})", os.path.basename(filename))
    wp, session = int(numbers.group(1)), int(numbers.group(2))
    
    with open(filename, 'rb') as fh:
        text = fh.read().decode('utf-8')

    pbar.set_description(f"Loaded transcript: {session:03d}/{wp}, from {filename}\n", refresh=False)

    lines = text.split('\n')

    # trigger to skip lines until date is captured
    date_captured = False
    # trigger to skip lines until in_session mark is matched
    in_session = False

    # poi
    poi = False
    issue = None
    issue_start = False  

    # variable captures contain new speaker if new speaker is detected
    new_speaker = None
    # contains current speaker, to use actual speaker and not speaker that interrupts speech
    current_speaker = None
    speaker_regex = None

    # trigger to check whether a interjection is found
    interjection = False
    interjection_complete = None

    # dummy variables and categorial variables to characterize speaker
    president = False
    executive = False
    servant = False
    party = None
    role = None

    # counts to keep order
    seq = 0
    sub = 0

    # contains list of dataframes, one df = one speech
    speeches = []

    for line, has_more in helper.lookahead(lines):
        # to avoid whitespace before interjections; like ' (Heiterkeit bei SPD)'
        line = line.lstrip()

        # grabs date, goes to next line until it is captured
        if not date_captured and DATE_CAPTURE.search(line):
            date = DATE_CAPTURE.search(line).group(1)
            date = datetime.strptime(date, '%d.%m.%Y').strftime('%Y-%m-%d')
            date_captured = True
            continue
        elif not date_captured:
            continue
        if not in_session and BEGIN_MARK.search(line):
            in_session = True
            continue
        elif not in_session:
            continue
        
        # Check whether previous line contained a online issue that may continue in this line
        if issue_start and not POI_ONE_LINER.match(line) and line.lstrip() != "":
            issue_start = False
            
        if poi:
            if POI_ONE_LINER.match(line):
                if POI_ONE_LINER.match(line).group(1):
                    issue = issue + ' ' + POI_ONE_LINER.match(line).group(1)
                poi = False
            else:
                issue = issue + ' ' + line
            issue = (issue.replace('<poi_begin>', '')
                        .replace('<poi_end>', '')
                        .replace('<interjection_begin>', '')
                        .replace('<interjection_end>', '')
                        .replace('  ', ' ')
                        .replace('- ', '')
                        )

        # detects speaker, if no interjection is found:
        if '<poi_begin>' in line and not interjection:
            if CHAIR_MARK.match(line):
                speaker_regex = CHAIR_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(2)).replace('<poi_begin>', '')
                president = True
                executive = False
                servant = False
                party = None
                role = 'chair'
                speaker_detected = True
            elif EXECUTIVE_MARK.match(line):
                speaker_regex = EXECUTIVE_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(1)).replace('<poi_begin>', '')
                role = 'executive'
                party = None
                president = False
                executive = True
                servant = False
                speaker_detected = True
            elif EXECUTIVE_MARK_SECOND.match(line):
                speaker_regex = EXECUTIVE_MARK_SECOND.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(1)).replace('<poi_begin>', '')
                party = None
                president = False
                executive = True
                servant = False
                role = 'executive'
                speaker_detected = True
            elif OFFICIALS_MARK.match(line):
                speaker_regex = OFFICIALS_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(2)).replace('<poi_begin>', '')
                party = None
                president = False
                executive = False
                servant = True
                role = speaker_regex.group(1)
                speaker_detected = True
            elif SPEAKER_MARK.match(line):
                speaker_regex = SPEAKER_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(1)).rstrip(')').rstrip('*').replace('<poi_begin>', '')
                president = False
                executive = False
                servant = False
                party = speaker_regex.group(2)
                role = 'mp'
                speaker_detected = True
            elif CONSTITUTIONAL_COURT_MARK.match(line):
                speaker_regex = CONSTITUTIONAL_COURT_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(1)).rstrip(')').rstrip('*').replace('<poi_begin>', '')
                president = False
                executive = False
                party = None
                role = 'president of constitutional court'
                speaker_detected = True
            else:
                if POI_ONE_LINER.match(line):
                    
                    if issue_start:
                        issue = (issue + ' ' + POI_ONE_LINER.match(line).group(1))
                    else:
                        issue = (POI_ONE_LINER
                            .match(line)
                            .group(1))
                        issue_start = True
                else:
                    issue = line
                    poi = True

                issue = (issue.replace('<poi_begin>', '')
                        .replace('<poi_end>', '')
                        .replace('<interjection_begin>', '')
                        .replace('<interjection_end>', '')
                        .replace('  ', ' ')
                        .replace('- ', '')
                        )

            line = line.replace('<poi_begin>', '').replace('<poi_end>', '')
            if speaker_detected:
                new_speaker = (new_speaker
                               .split(':')[0]
                               .replace('<poi_end>', '')
                               .replace('*)', '')
                               .strip()
                               )
                new_speaker = re.sub(' +', ' ', new_speaker)

        # saves previous speech if new speaker  or end of session is detected:
        if new_speaker is not None and current_speaker is not None:
            if new_speaker != current_speaker or END_MARK.search(line) or not has_more:
                # joins list elements that are strings
                text = ''.join(text)
                # removes whitespace duplicates
                text = re.sub(' +', ' ', text)
                # removes whitespaces at the beginning and end
                text = text.strip()
                text = text.replace('<interjection_begin>', '')
                text = text.replace('<interjection_end', '')
                text = text.replace('<poi_end>', '')
                text = text.replace('<poi_begin', '')
                # # 
                # text = re.sub('-(?=[a-z])', '', text)
                
                if text:
                    append_speech(speeches, current_speaker, current_party, text, seq, sub, current_executive, current_servant, wp, session, current_president, current_role, BUNDESLAND, interjection, date, issue) 
                    
                # stops iterating over lines, if end of session is reached e.g. Schluss: 17:16 Uhr
                if END_MARK.search(line):
                    in_session = False
                    break
                
                # Tracking speeches
                seq += 1
                sub = 0
                current_speaker = None
                
        # adds interjections to the data in such a way that order is maintained
        if INTERJECTION_MARK.match(line) and not interjection:
        # skips lines that start with brackes for abbreviations at the beginning of line e.g. '(EU) Drucksache [...]'
            # variable contains the number of lines an interjection covers
            interjection_length = 0
            # saves speech of speaker until this very interjection
            if not interjection_complete and current_speaker is not None:
                # joins list elements of strings
                text = ''.join(text)
                # removes whitespace duplicates
                text = re.sub(' +', ' ', text)
                # removes whitespaces at the beginning and end
                text = text.strip()
                text = re.sub('-(?=[a-z])', '', text)
                text = text.replace('<interjection_begin>', '').replace('<interjection_end>', '')
                text = text.replace('<poi_begin>', '').replace('<poi_end>', '')
                if text:
                    append_speech(speeches, current_speaker, current_party, text, seq, sub, current_executive, current_servant, wp, session, current_president, current_role, BUNDESLAND, interjection, date, issue) 

            sub += 1
            interjection = True
            interjection_text = []
        # special case: interjection
        if interjection:
            # either line ends with ')' and opening and closing brackets are equal or we had two empty lines in a row
            if '<interjection_end>' in line:
                # to avoid an error, if interjection is at the beginning without anybod have started speaking
                # was only relevant for bavaria so far.
                if current_speaker is not None:
                    if line and not line.isspace():
                        interjection_text.append(line)
                    interjection_text = [i.rstrip('-') if i.endswith('-') else i for i in interjection_text]
                    interjection_text = ''.join(interjection_text)
                    # removes whitespace duplicates
                    interjection_text = re.sub(' +', ' ', interjection_text)
                    # removes whitespaces at the beginning and end
                    interjection_text = interjection_text.strip()
                    interjection_text = re.sub('-(?=[a-z])', '', interjection_text)
                    interjection_text = interjection_text.replace('<interjection_begin>', '')
                    interjection_text = interjection_text.replace('<interjection_end>', '')
                    if interjection_text:
                        append_speech(speeches, current_speaker, current_party, interjection_text, seq, sub, current_executive, current_servant, wp, session, current_president, current_role, BUNDESLAND, interjection, date, issue)
                        
                    sub += 1
                    interjection_length += 1
                    ls_interjection_length.append([interjection_length, wp, session, seq, sub, current_speaker, interjection_text])
                interjection = False
                interjection_complete = True
                interjection_skip = False
                continue
            else:
                if line and not line.isspace():
                    interjection_text.append(line)
                interjection_length += 1
                continue
        if current_speaker is not None:
            if interjection_complete:
                interjection_complete = None
                text = []
                line = helper.cleans_line(line)
                if line and not line.isspace():
                    text.append(line)
                continue
            else:
                current_role = current_role.strip()

                line = helper.cleans_line(line)
                if line and not line.isspace():
                    text.append(line)
                continue

        if new_speaker is not None:
            if ":* " in line:
                line = line.split(':* ', 1)[-1]
            elif ":" in line:
                line = line.split(':', 1)[-1]
            line = helper.cleans_line(line)
            text = []
            if line and not line.isspace():
                text.append(line)
            current_speaker = new_speaker
            current_party = party
            current_president = president
            current_executive = executive
            current_servant = servant
            current_role = role
            speaker_detected = False
        if not has_more and in_session:
            errormessage = f"WP {wp} Session {session}: no match for end mark -> ERROR"
            print("\n",errormessage)
            errormessages.append(errormessage)

    pd_session_speeches = pd.concat(speeches)
    if pd_session_speeches.loc[pd_session_speeches.interjection==True].interjection.count() < 50 or len(pd_session_speeches.seq.unique()) < 20:
        errormessage = f"Warning - Session {session:03d}/{wp}: Only {len(pd_session_speeches.seq.unique())} speeches and {pd_session_speeches.loc[pd_session_speeches.interjection==True].interjection.count()} interjections"
        print("\n",errormessage)
        errormessages.append(errormessage)
        
    ls_speeches.append(pd_session_speeches)

pd_speeches = pd.concat(ls_speeches).reset_index()
pd_speeches.to_csv(os.path.join(DATA_PATH, BUNDESLAND + '.csv'))
pd_speeches.sample(250).to_csv(os.path.join(DATA_PATH, BUNDESLAND + '_sample.csv'))

for mess in errormessages:
    print(mess)
    
# checks
# interjection length
# idx = [i for i, e in enumerate(ls_interjection_length) if e[0] <= 10 and e[0] > 8]

# #text length
# idx_txt = [i for i, e in enumerate(ls_text_length[0:10]) if e[0] > 15]

# pd_speeches.loc[:, ['wp', 'session', 'seq']].groupby(['wp', 'session']).max()

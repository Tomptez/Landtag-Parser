# coding: utf-8
import os
import locale
import re
import logging
import pandas as pd
from datetime import datetime
from tqdm import tqdm

from lib import helper, hh_parts

log = logging.getLogger(__name__)

locale.setlocale(locale.LC_TIME, "de_DE.utf-8")

BUNDESLAND = 'HH'

DATA_PATH = f"data/{BUNDESLAND}"

# regular expressions to capture speeches 
# of one session Beginn: Beginn der Sitzung:
BEGIN_STRING = r'(Beginn der Sitzung|Beginn|Schluss|Ende):\s+\d\d[.:]\d\d\s+Uhr'
END_STRING = r'Ende:\s+(Ende.?)?[0-9]{1,2}[.:][0-9]{1,2}\s+Uhr'
CHAIR_STRING = r'^(Alterspräsident(?:in)?|Präsident(?:in)?|Erste(?:r)?\s+Vizepräsident(?:in)?|Vizepräsident(?:in)?)\s+(.+?)<poi_end>'
SPEAKER_STRING = r'(.+?)\s?<poi_end>(?:\s+)?[\(]?(CDU|SPD|(?:DIE\s+)?LINKE|GAL|GR(?:-|Ü(?:-|NE))|FDP|A[fF]D|fraktionslos)[\]\)]?(?:\s+\((?:fortfahrend|unterbrechend))?'
EXECUTIVE_STRING = r'^(Senator(?:in)?|Erste(?:r)?\s+Bürgermeister(?:in)?|Zweite(?:r)?\s+Bürgermeister(?:in)?)\s+(.+)'
OFFICIALS_STRING = r'^(Staatsrat|Staatsrätin)\s+(.+?):'
NOTE_STRING = r'^(?:(?:Zwischenbemerkung|Zwischenfrage)\s+von\s+)(.+)(?:\s+)?(?:<poi_end>)?(CDU|SPD|DIE\s+LINKE|GAL|GR(?:-|Ü(?:-|NE))|FDP|AfD|fraktionslos)?'
CONTINUATION_STRING = r'^(.+)(?:\s+)?<poi_end>(?:\(fortfahrend|\(unterbrechend)'

# compilation of regular expressions
# advantage combination of strings is possible
BEGIN_MARK = re.compile(BEGIN_STRING)
END_MARK = re.compile(END_STRING)
CHAIR_MARK = re.compile(CHAIR_STRING)
SPEAKER_MARK = re.compile(SPEAKER_STRING)
EXECUTIVE_MARK = re.compile(EXECUTIVE_STRING)
OFFICIALS_MARK = re.compile(OFFICIALS_STRING)
INTERJECTION_MARK = re.compile(r'^\(')
INTERJECTION_END = re.compile(r'\)$')
DATE_CAPTURE = re.compile(r'([0-9]{1,2}\.(?:\s+)?(?:.+?|)(?:\s+)?[0-9]{4})')
POI_ONE_LINER = re.compile(r'(.+?)?<poi_end>(?:.+)?')
NOTE_MARK = re.compile(NOTE_STRING)
CONTINUATION_MARK =  re.compile(CONTINUATION_STRING)

files = [os.path.join(dp, f) for dp, dn, fn in os.walk(os.path.expanduser(os.path.join(DATA_PATH, "txt"))) for f in fn if f.endswith("xml.txt")]

# For testing at the end
ls_speeches = []
ls_interjection_length = []
ls_text_length = []
dict_speaker = {}

errormessages = []

def remove_indentation(text):
    if text != "" and text is not None:
        return text.replace("<indentation_begin>", "").replace("<indentation_end>", "")
    else:
        return text

def append_speech(speeches, current_speaker, current_party, text, seq, sub, current_executive, current_servant, wp, session, current_president, current_role, BUNDESLAND, interjection, date, issue):
    issue = remove_indentation(issue)
    text = remove_indentation(text)
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
        if not date_captured and DATE_CAPTURE.search(line):
            date = DATE_CAPTURE.search(line).group(1)
            try:
                date = datetime.strptime(date, '%d. %B %Y').strftime('%Y-%m-%d')
            except:
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

        if poi:
            if POI_ONE_LINER.match(line):
                if POI_ONE_LINER.match(line).group(1):
                    issue = issue + ' ' + POI_ONE_LINER.match(line).group(1)
                poi = False
            else:
                issue = issue + ' ' + line

        if '<poi_begin>' in line and not poi and not interjection:
            line = line.replace('<poi_begin>', '')
            if CHAIR_MARK.match(line):
                speaker_regex = CHAIR_MARK.match(line)
                new_speaker = helper.cleans_speaker_hh(speaker_regex.group(2))
                president = True
                executive = False
                servant = False
                party = None
                role = 'chair'
            elif EXECUTIVE_MARK.match(line):
                speaker_regex = EXECUTIVE_MARK.match(line)
                new_speaker = helper.cleans_speaker_hh(speaker_regex.group(2))
                role = 'executive'
                party = None
                president = False
                executive = True
                servant = False
            elif OFFICIALS_MARK.match(line):
                speaker_regex = OFFICIALS_MARK.match(line)
                new_speaker = helper.cleans_speaker_hh(speaker_regex.group(2))
                party = None
                president = False
                executive = False
                servant = True
                role = 'servant'
            elif SPEAKER_MARK.match(line):
            # if any(person in line for person in abg):
                speaker_regex = SPEAKER_MARK.match(line)
                new_speaker = helper.cleans_speaker_hh(speaker_regex.group(1))
                president = False
                executive = False
                servant = False
                party = speaker_regex.group(2)
                role = 'mp'
                dict_speaker[new_speaker] = party
            elif NOTE_MARK.match(line):
                speaker_regex = NOTE_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(1))
                president = False
                executive = False
                servant = False
                party = speaker_regex.group(2)
                new_speaker, party = hh_parts.finds_party(new_speaker.replace('<poi_end>', '').strip(), party, date, wp, line, dict_speaker)
                role = 'mp'
            elif CONTINUATION_MARK.match(line):
                speaker_regex = CONTINUATION_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(1)).strip()
                president = False
                executive = False
                servant = False
                party = None
                new_speaker, party = hh_parts.finds_party(new_speaker, party, date, wp, line, dict_speaker)
                role = 'mp'
            elif line.startswith('['):
                if POI_ONE_LINER.match(line):
                    issue = POI_ONE_LINER.match(line).group(1)
                else:
                    issue = line
                    poi = True

            line = line.replace('<poi_end>', '')

        if not poi and current_speaker:
            if new_speaker:
                new_speaker = (new_speaker
                               .replace('<poi_end>', '')
                               .replace('(fortfahrend)', '')
                               .replace('*', '')
                               .replace(')', '')
                               .replace('Stapel-', 'Stapelfeldt')
                               .strip()
                               )
                new_speaker = re.sub(' +', ' ', new_speaker)
                if party:
                    party = party.replace('AFD', 'AfD').replace('GRÜ-', 'GRÜNE')
                    if party == 'LINKE':
                        party ='DIE LINKE'

        # saves previous speech if new speaker  or end of session is detected:
        if new_speaker is not None and current_speaker is not None:
            if new_speaker != current_speaker or END_MARK.search(line) or not has_more:
                text_length = len(text)
                text = ''.join(text)
                # removes whitespace duplicates
                text = re.sub(' +', ' ', text)
                # removes whitespaces at the beginning and end
                text = text.strip()
                if text:
                    append_speech(speeches, current_speaker, current_party, text, seq, sub, current_executive, current_servant, wp, session, current_president, current_role, BUNDESLAND, interjection, date, issue) 
                    ls_text_length.append([text_length, wp, session, seq, sub, current_speaker, text])
                    
                if END_MARK.search(line):
                    in_session = False
                    break
                
                # Tracking speeches
                seq += 1
                sub = 0
                current_speaker = None
                
        # adds interjections to the data in such a way that order is maintained
        if '<interjection_begin>' in line:
            line = line.replace('<interjection_begin>', '')
            
            # concatenates lines to one string
            interjection_length = 0
            if not interjection_complete and current_speaker is not None:
                    text_length = len(text)
                    text = ''.join(text)
                    # removes whitespace duplicates
                    text = re.sub(' +', ' ', text)
                    # removes whitespaces at the beginning and end
                    text = text.strip()
                    text = re.sub('-(?=[a-z])', '', text)
                    if text:
                        append_speech(speeches, current_speaker, current_party, text, seq, sub, current_executive, current_servant, wp, session, current_president, current_role, BUNDESLAND, interjection, date, issue) 
                        ls_text_length.append([text_length, wp, session, seq, sub, current_speaker, text])
            sub += 1
            interjection = True
            interjection_text = []
            
        if interjection:
            if '<interjection_end>' in line:
                line = line.replace('<interjection_end>', '')
                
                if current_speaker is not None:
                    if line and not line.isspace():
                        interjection_text.append(line)
                    interjection_text = [i + ' ' if not i.endswith('-') else i.replace('-', '') for i in interjection_text]
                    interjection_text = ''.join(interjection_text)
                    # removes whitespace duplicates
                    interjection_text = re.sub(' +', ' ', interjection_text)
                    # removes whitespaces at the beginning and end
                    interjection_text = interjection_text.strip()
                    interjection_text = re.sub('-(?=[a-z])', '', interjection_text)
                    
                    append_speech(speeches, current_speaker, current_party, interjection_text, seq, sub, current_executive, current_servant, wp, session, current_president, current_role, BUNDESLAND, interjection, date, issue)
                    
                    interjection_length += 1
                    ls_interjection_length.append([interjection_length, wp, session, seq, sub, current_speaker, interjection_text])
                    sub += 1
                    
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
# idx = [i for i, e in enumerate(ls_interjection_length)
#        if e[0] >= 8 and e[0] < 10]

# #text length
# idx_txt = [i for i, e in enumerate(ls_text_length[0:10]) if e[0] > 15]

# pd_speeches.loc[:, ['wp', 'session', 'seq']].groupby(['wp', 'session']).max()
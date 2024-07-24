# coding: utf-8
import os
import locale
import re
import logging
import pandas as pd
from datetime import datetime
import sys
from tqdm import tqdm

log = logging.getLogger(__name__)

from lib import helper

locale.setlocale(locale.LC_TIME, "de_DE.utf-8")

BUNDESLAND = 'SN'
DATA_PATH = f"data/{BUNDESLAND}"

# regular expressions to capture speeches of one session
BEGIN_STRING = r'^(?:<interjection_begin>)?\((Beginn)|(Fortsetzung)\s+der\s+Sitzung:?\s+[0-9]{1,2}[.:][0-9]{1,2}'
END_STRING = r'^(?:<interjection_begin>)?\((?:Schluss|Unterbrechung)\s+(?:des\s+ersten\s+Teils\s+)?der\s+Sitzung(?::?\s+)?[0-9]{1,2}[.:][0-9]{1,2}|^(<interjection_begin>)?\(Schluss\s+.?der\s+Sitzung:'
CHAIR_STRING = r'^<poi_begin>(Alterspräsident(?:in)?|Präsident(?:in)?|(?:[0-9]\.)?(?:Erste)?|(?:Zweite)?|(?:Dritte)?|(?:Vierte)?(?:\s+)?Vizepräsident(?:in)?)\s+(.+?):'
SPEAKER_STRING = r'^<poi_begin>(.+?)\,\s+(CDU|SPD|GRÜNE|Linksfraktion|(?:Die\s+)?Linke|DIE(?:\s+)?LINKE|FDP|NPD|AfD|fraktionslos):'
EXECUTIVE_STRING = r'^<poi_begin>(.+?),\s+(Staatsminister(?:in)?|Ministerpräsident(?:in)?).+$'
OFFICIALS_STRING = r'^<poi_begin>(.+?),\s+(Staatssekretär(?:in)?)'
COMISSIONER_STRING = r'^<poi_begin>(.+?),\s+(Sächsischer\s+(?:Ausländer|Datenschutz).*$)'
DATE_STRING = r'^[0-9]\.'

# compilation of regular expressions
# advantage combination of strings is possible
BEGIN_MARK = re.compile(BEGIN_STRING)
END_MARK = re.compile(END_STRING)
CHAIR_MARK = re.compile(CHAIR_STRING)
SPEAKER_MARK = re.compile(SPEAKER_STRING)
EXECUTIVE_MARK = re.compile(EXECUTIVE_STRING)
OFFICIALS_MARK = re.compile(OFFICIALS_STRING)
COMISSIONER_MARK = re.compile(COMISSIONER_STRING)
INTERJECTION_MARK = re.compile(r'^<interjection_begin>\(')
INTERJECTION_END = re.compile(r'\)$')
DATE_CAPTURE = re.compile(r'([0-9]{1,2}\.(?:\s+)?.+[0-9]{4})')
DATE_CHECK = re.compile(DATE_STRING)
POI_ONE_LINER = re.compile(r'(.+?)?<poi_end>(?:.+)?')

txt_folder = os.path.join(DATA_PATH, "txt")
files = sorted([os.path.join(dp, f) for dp, dn, fn in os.walk(txt_folder) for f in fn if f.endswith("xml.txt")])

if files == []:
    print(f"No files found in {txt_folder}")
    sys.exit()

# For testing at the end
ls_speeches = []
ls_interjection_length = []
ls_text_length = []

errormessages = []


def remove_indentation(text):
    return text.replace("<indentation_begin>", "").replace("<indentation_end>", "")

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
    numbers = re.search(r"^(\d)_\D+_(\d{1,3})", os.path.basename(filename))
    wp, session = int(numbers.group(1)), int(numbers.group(2))

    with open(filename, 'rb') as fh:
        text = fh.read().decode('utf-8')

    pbar.set_description(f"Loading transcript: {session:03d}/{wp}, from {filename}\n", refresh=False)

    lines = text.split('\n')

    # trigger to skip lines until date is captured
    date_captured = False
    # trigger to skip lines until in_session mark is matched
    in_session = False

    # poi
    poi = False
    poi_prev = False
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

    endend_with_interjection = False

    # contains list of dataframes, one df = one speech
    speeches = []

    for line, has_more in helper.lookahead(lines):
        if line and line == line.rstrip():
            line = line + ' '
        # to avoid whitespace before interjections; like ' (Heiterkeit bei SPD)'
        line = line.lstrip()

        # grabs date, goes to next line until it is captured
        if not date_captured and DATE_CAPTURE.search(line):
            date = DATE_CAPTURE.search(line).group(1)
            try:
                date = datetime.strptime(date, '%d. %B %Y').strftime('%Y-%m-%d')
            except ValueError:
                try:
                    date = datetime.strptime(date, '%d.%B %Y').strftime('%Y-%m-%d')
                except ValueError:
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

        #ignores header lines and page numbers e.g. 'Landtag Mecklenburg-Vorpommer - 6. Wahlperiode [...]'
        if line.replace('<interjection_begin>', '').replace('<interjection_end>', '').strip().isdigit():
           continue

        if poi:
            if POI_ONE_LINER.match(line):
                if POI_ONE_LINER.match(line).group(1):
                    issue = issue + ' ' + POI_ONE_LINER.match(line).group(1)
                issue = issue.replace('<poi_begin>', '')
                issue = issue.replace('<poi_end>', '')
                issue = remove_indentation(issue)
                poi = False
                # poi_prev = True
                line = line.replace('<poi_end>', '')
            else:
                issue = issue + ' ' + line
                issue = remove_indentation(issue)

        # detects speaker, if no interjection is found:
        if '<poi_begin>' in line and not interjection:
            if CHAIR_MARK.match(line):
                speaker_regex = CHAIR_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(2))
                president = True
                executive = False
                servant = False
                party = None
                role = 'chair'
                poi_prev = False
            elif EXECUTIVE_MARK.match(line):
                speaker_regex = EXECUTIVE_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(1))
                role = 'executive'
                party = None
                president = False
                executive = True
                servant = False
                poi_prev = False
            elif OFFICIALS_MARK.match(line):
                speaker_regex = OFFICIALS_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(1))
                party = None
                president = False
                executive = False
                servant = True
                role = 'state secretary'
                poi_prev = False
            elif COMISSIONER_MARK.match(line):
                speaker_regex = COMISSIONER_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(1))
                party = None
                president = False
                executive = False
                servant = False
                role = 'commissioner'
                poi_prev = False
            elif SPEAKER_MARK.match(line):
                speaker_regex = SPEAKER_MARK.match(line)
                new_speaker = re.sub(' +', ' ', speaker_regex.group(1)).rstrip(')').rstrip('*')
                president = False
                executive = False
                servant = False
                party = speaker_regex.group(2)
                role = 'mp'
                poi_prev = False
            else:
                if POI_ONE_LINER.match(line):
                    issue = POI_ONE_LINER.match(line).group(1)
                    issue = issue.replace('<poi_begin>', '').replace('<poi_end>', '')
                    issue = remove_indentation(issue)
                else:
                    issue = remove_indentation(line)
                    poi = True

            if new_speaker:
                new_speaker = new_speaker.replace(':', '').replace('<poi_end>', '').strip()
                if party:
                    party = party.replace('BÜNDNIS 90', 'GRÜNE').replace('BÜNDNISGRÜNE', 'GRÜNE').replace('Linksfraktion', 'DIE LINKE')

        # saves previous speech if new speaker  or end of session is detected:
        if new_speaker is not None and current_speaker is not None:
            if new_speaker != current_speaker or END_MARK.search(line) or not has_more:
                # length for optional check at the end
                text_len = len(text)
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

                ls_text_length.append([text_len, wp, session, seq, sub, current_speaker])
                
                if END_MARK.search(line):
                    in_session = False
                    break
                
                # Tracking speeches
                seq += 1
                sub = 0
                current_speaker = None
                
        # adds interjections to the data in such a way that order is maintained
        if INTERJECTION_MARK.match(line) and not interjection and not '<poi_begin>' in line:
        # skips lines that start with brackes for abbreviations at the beginning of line e.g. '(EU) Drucksache [...]'
            # variable contains the number of lines an interjection covers
            interjection_length = 0
            # saves speech of speaker until this very interjection
            if not interjection_complete and current_speaker is not None:
                text_len = len(text)
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

                    ls_text_length.append([text_len, wp, session, seq, sub, current_speaker, text])

            #
            sub += 1
            interjection = True
            interjection_text = []

        if interjection:
            if '<interjection_end>' in line:
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
                    interjection_text = interjection_text.replace('<interjection_begin>', '').replace('<interjection_end>', '')
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
                line = line.replace('<interjection_begin>', '').replace('<interjection_end>', '')
                if line:
                    interjection_text.append(line)
                    interjection_length += 1
                continue
        if current_speaker is not None and not endend_with_interjection:
            if interjection_complete:
                interjection_complete = None
                text = []
                line = helper.cleans_line_sn(line)
                
                ## Todo check
                if line and not line.isspace():
                    text.append(line)
                continue
            else:
                current_role = current_role.strip()
                line = remove_indentation(line)
                line = line.replace('<interjection_end>', '')
                line = helper.cleans_line_sn(line)
                if line and not line.isspace():
                    text.append(line)
                continue

        if new_speaker is not None:
            if not endend_with_interjection:
                if ":* " in line:
                    line = line.split(':* ', 1)[-1]
                elif ":" in line:
                    line = line.split(':', 1)[-1]
                if line.startswith("<poi_end"):
                    line = line[9:]
            line = helper.cleans_line_sn(line)
            text = []
            text.append(line)
            current_speaker = new_speaker
            current_party = party
            current_president = president
            current_executive = executive
            current_servant = servant
            current_role = role
            endend_with_interjection = False
            interjection_complete = None
        if not has_more and in_session:
            errormessage = f"WP {wp} Session {session}: no match for end mark -> ERROR"
            print("\n",errormessage)
            errormessages.append(errormessage)
    
    pd_session_speeches = pd.concat(speeches)
    if pd_session_speeches.loc[pd_session_speeches.interjection==True].interjection.count() < 50 or len(pd_session_speeches.seq.unique()) < 20:
        errormessage = f"Warning - WP {wp} Session {session}: Only {len(pd_session_speeches.seq.unique())} speeches and {pd_session_speeches.loc[pd_session_speeches.interjection==True].interjection.count()} interjections"
        print("\n",errormessage)
        errormessages.append(errormessage)
        
    ls_speeches.append(pd_session_speeches)

pd_speeches = pd.concat(ls_speeches).reset_index()
pd_speeches.to_csv(os.path.join(DATA_PATH, BUNDESLAND + '.csv'), index=False)
pd_speeches.sample(250).to_csv(os.path.join(DATA_PATH, BUNDESLAND + '_sample.csv'))

for mess in errormessages:
    print(mess)

# checks
# interjection length
# idx = [i for i, e in enumerate(ls_interjection_length) if e[0] > 8]

# #text length
# idx_txt = [i for i, e in enumerate(ls_text_length) if e[0] > 15]

# pd_speeches.loc[:, ['wp', 'session', 'seq']].groupby(['wp', 'session']).max()
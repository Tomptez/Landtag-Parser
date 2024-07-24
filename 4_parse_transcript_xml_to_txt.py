import os
from operator import itemgetter
import re
import sys
import xml.etree.cElementTree as ET
import json

# only one set of pages:
# text x0: 57
# interjection: 85
# text x0: 312
# interjection: 340

def lookahead(iterable):
    """
    Pass through all values from the given iterable, augmented by the
    information if there are more values to come after the current one
    (True), or if it is the last value (False).
    """
    # Get an iterator and pull the first value.
    it = iter(iterable)
    last = next(it)
    # Run the iterator to exhaustion (starting from the second value).
    for val in it:
        # Report the *previous* value (more to come).
        yield last, True
        last = val
    # Report the last value.
    yield last, False


def parseXML(xml_in, params, BUNDESLAND):
    """
    converts xml files to txt while retaining indentations and speaker informations
    
    Keyword arguments:
    xml_in: plenary protocol as XML file as converted by pxfminer.six pdf2txt
    params: dict with values "header_bound", "indentation_bound_left", "indentation_bound_right" which is created in analyze_layout.py
    BUNDESLAND: "HH", "SN", "NRW" are tested
    
    """
    # import pdb; pdb.set_trace()
    # if two fragments of text are within LINE_TOLERANCE of each other they're
    # on the same line

    NO_INTERJECTION = re.compile(r'^(Beginn der Sitzung|Beginn|Schluss|Ende):\s+\d\d[.:]\d\d\s+Uhr')

    # ENDING_MARK = re.compile('(\(Schluss der Sitzung:.\d{1,2}.\d{1,2}.Uhr\).*|Schluss der Sitzung)')

    debug = False

    found_ending_mark = False

    # get the page elements
    tree = ET.ElementTree(file=xml_in)
    pages = tree.getroot()

    if pages.tag != "pages":
        sys.exit("ERROR: pages.tag is %s instead of pages!" % pages.tag)

    text = []
    # step through the pages
    for page in pages:
        # gets page_id
        page_id = page.attrib['id']

        # get all the textline elements
        textboxes = page.findall("./textbox")

        #print "found %s textlines" % len(textlines)
        # step through the textlines
        page_text = []

        interjection_left = params['indentation_bound_left'] - 1
        interjection_right = params['indentation_bound_right'] -1
        header_bound = params['header_bound'] -1 

        for textbox in textboxes:
            # get the boundaries of the textline
            textbox_bounds = [float(s) for s in textbox.attrib["bbox"].split(',')]
            #print "line_bounds: %s" % line_bounds

            # get all the texts in this textline
            lines = list(textbox)
            #print("found %s characters in this line." % len(chars))

            # combine all the characters into a single string
            textbox_text = ""
            poi = False
            for line, has_more in lookahead(lines):
                chars = list(line)
                for char in chars:
                    if poi:
                        if char.attrib:
                            if "Bold" not in char.attrib['font']:
                                textbox_text = textbox_text + '<poi_end>'
                                poi = False
                    elif char.attrib:
                        if "Bold" in char.attrib['font']:
                            textbox_text = textbox_text + '<poi_begin>'
                            poi = True
                    textbox_text = textbox_text + char.text
                if not has_more and poi:
                    textbox_text = textbox_text + '<poi_end>'

            textbox_text = textbox_text.replace('\n<poi_end>', '<poi_end>\n').replace('\t', ' ')
            textbox_text = re.sub(' +', ' ', textbox_text.strip())

            # removes header/footer
            if textbox_bounds[1] > header_bound and page_id not in ['1']:
                print('removed header ' + textbox_text)
                continue


            # save a description of the line
            textbox = {'left': textbox_bounds[0], 'top': textbox_bounds[1], 'text': textbox_text}

            condition_left_col = textbox['left'] > interjection_left and textbox['left'] < interjection_right-50
            condition_right_col = textbox['left'] > interjection_right
            if condition_left_col or condition_right_col:
                if textbox_text.lstrip().startswith('(') and not NO_INTERJECTION.match(textbox_text):
                    textbox['text'] = '<interjection_begin>' + textbox['text'] + '<interjection_end>'
                else:
                    textbox['text'] = '<indentation_begin>' + textbox['text'] + '<indentation_end>'

            # Make sure order is correct
            if textbox['left'] < interjection_right-50:
                textbox['top'] = textbox['top']+2000
            page_text.sort(key=itemgetter('top'), reverse=True)
            
            page_text.append(textbox)

        page_text = '\n\n'.join([e['text'] for e in page_text])

        text.append(page_text + '\n')

    # if not found_ending_mark:
    #     sys.exit('could not find closing mark; adjust regex')

    return text

def iteratesFiles(BUNDESLAND):    
    """
    iterates over XML files in data/BUNDESLAND/xml
    
    Keyword arguments:
    BUNDESLAND: "HH", "SN", "NRW" are tested
    """
    DATA_PATH = f"data/{BUNDESLAND}/xml"
    os.makedirs(f"data/{BUNDESLAND}/txt", exist_ok=True)
    files = [os.path.join(dp, f) for dp, dn, fn in os.walk(os.path.expanduser(DATA_PATH)) for f in fn if f.endswith(".xml")]
    
    with open(os.path.join(f"data/{BUNDESLAND}", "params_" + BUNDESLAND + ".json"), encoding="utf-8") as fp:
        params = json.loads(fp.read())
    for filename in sorted(files):
        output_name = filename.replace("/xml", "/txt").replace('.xml', '_xml.txt')
        #if os.path.exists(output_name):
        #   continue
        print(filename)
        result = parseXML(filename, params=params, BUNDESLAND=BUNDESLAND)
        
        with open(output_name, "w", encoding="utf-8") as fp:
            fp.writelines(result)
            

if __name__ == "__main__":
    iteratesFiles("SN")

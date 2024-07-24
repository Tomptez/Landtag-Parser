import os
import json
from collections import Counter
from tqdm import tqdm
from lib import layout_collector
import re
import random

def scans_layout_plenary_records(BUNDESLAND="NRW"):
    """
    creates file "params_{BUNDESLAND}.json" which is later used when converting XML to .txt to retain visual text informations (indentations etc.)
    
    Keyword arguments:
    BUNDESLAND: only "HH", "SN" and "NRW" were tested
    
    For other Bundesländer, HEADER_MARK may need to be changed
    For other Bundesländer, maybe the first page needs to be excluded for analysis
    """

    DATA_PATH = f"data/{BUNDESLAND}/pdf"

    # (x0, y0) -> Bottom left corner, (x1, y1) -> Top right corner
    x0_occurences = []
    x1_occurences = []
    text_boxes = []
    y0_occurences = []
    y1_occurences = []

    files = [os.path.join(dp, f) for dp, dn, fn in os.walk(os.path.expanduser(DATA_PATH)) for f in fn if f.endswith(".pdf")]

    # Check 3 random pds
    for filename in tqdm(random.sample(files, 6)):
        print(filename)
    # Open a PDF file
        pages, x0_occurences, x1_occurences, text_boxes, y0_occurences, y1_occurences = layout_collector.get_pages(filename, 
        	x0_occurences=x0_occurences, x1_occurences=x1_occurences, 
        	text_boxes=text_boxes,
        	y0_occurences=y0_occurences, y1_occurences=y1_occurences)

    x0_occurences_ls = [item for sublist in x0_occurences for item in sublist]
    text_boxes_ls = [item for sublist in text_boxes for item in sublist]
    y0_occurences_ls = [item for sublist in y0_occurences for item in sublist]
    
    header_bound_y0 = []
    indent_x0 = []
    
    HEADER_MARK = re.compile(r"^(?:Plenarprotokoll\s+[0-9]{2}\/[0-9]{1,3})|(\d{1,3}. Wahlperiode\s+\W\s+\d{1,3})")
    for i, tx in enumerate(text_boxes_ls):
        
        if HEADER_MARK.match(tx):
            header_bound_y0.append(y0_occurences_ls[i])
        if "(Beifall" in tx:
            indent_x0.append(x0_occurences_ls[i])
    
    counted = Counter(indent_x0)
    
    # Calculate the minimum indention of interjections in the right column        
    right_indent_counted = {k: v for k, v in counted.items() if k > (max(indent_x0)/2)}
    right_indent_counted = dict(sorted(right_indent_counted.items(), key=lambda item: item[0]))
    right_indent_margin = right_indent_counted.keys()
    
    # Remove exeptions for min indention for left and right applause (may not be necessary)
    while counted[min(indent_x0)] < 2:
        print("remove left indent", min(indent_x0), "occurences:", counted[min(indent_x0)])
        indent_x0 = [i for i in indent_x0 if i != min(indent_x0)]
    while right_indent_counted[min(right_indent_margin)] < 2:
        print("remove right indent", min(right_indent_margin), "occurences:", counted[min(right_indent_margin)])
        right_indent_margin = [i for i in right_indent_margin if i != min(right_indent_margin)]
    
    # Print results
    print("Beifall indent min:", min(indent_x0), "Beifall indent right min:", min(right_indent_margin))
    print("header_bound min:", min(header_bound_y0), "header_bound max", max(header_bound_y0))
    
    # Create parameter file for next step
    params = {"header_bound": min(header_bound_y0), "indentation_bound_left":min(indent_x0), "indentation_bound_right":min(right_indent_margin)}

    with open(f"data/{BUNDESLAND}/params_{BUNDESLAND}.json", mode = "w") as f:
        f.write(json.dumps(params))
    
if __name__ == "__main__":
    scans_layout_plenary_records("SN")

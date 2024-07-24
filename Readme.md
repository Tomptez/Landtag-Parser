# Landtag parser - German federal parliament data

This repository contains a number of scripts to extract a complete dataset for German federal state parliaments (Landtag), namely Hamburg, Sachsen/Saxony and Nord Rhein-Westfalen/North Rhine-Westphalia. While only tested in these three cases, it could easily be extended for other parliaments as well, though some additional work would be required (see below).

The code build on the previous work by [panoptikum for the  plenary_record_parser](https://github.com/panoptikum/plenary_record_parser/).

While the code here draws from its approach and reuses some parts, it has largely been rewritten with the goal of building a robust, documented and reproducible approach of parsing federal state plenary data for scientific usage.

Explanation of the files:

1_retrieve.py - A script to download plenary documents (for Hamburg and North Rhine-Wesphalia only)

2_analyze_layout.py - Uses sample files to analyze the layout of the pdf and identify size of margins and identions

3_parser_wrapper_to_xml.py - Bulk converts PDF files to XML

4_parse_transcript_xml_to_txt.py - Bulk converts XML files to TXT and retains information of the pdf-layout based on the information in params_{STATE}.json (created by1_retrieve.py)

5_plenary_record_parser_txt_{STATE}.py - Creates a .csv file from the previous TXT files. These are separate for each state to account for differences in the layout and wording in each state and requires regex that is adapted for each state. To expand the code for other states, these need to be changed accordingly.

Code in lib are helper files which are taken from panoptikum (see above) and pdfminer 
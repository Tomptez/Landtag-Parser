import urllib.request
import time
from tqdm import tqdm
import os
import requests
from bs4 import BeautifulSoup
from random import randrange

# Only HH and NRW tested and working, SN not working
WPS = [22]
BUNDESLAND = "HH"
SEARCH_HH_URL = 'https://www.buergerschaft-hh.de/parldok/dokumentennummer'

def format_url_filename(wp, n):
    filename = f"data/{BUNDESLAND}/pdf"
    if BUNDESLAND == "NRW":
        filename += f"/MMP{wp}-{n}.pdf"
        url = f"https://www.landtag.nrw.de/portal/WWW/dokumentenarchiv/Dokument/MMP{wp}-{n}.pdf"
    elif BUNDESLAND == "HH":
        filename += f"/plenarprotokoll{wp}-{n}.pdf"
        postreq = {'DokumentenArtId': 2, "LegislaturPeriodenNummer": wp, "DokumentenNummer": n}
        search_result = requests.post(SEARCH_HH_URL, json = postreq)
        soup = BeautifulSoup(search_result.text, 'html.parser')
        res = soup.find(attrs={"headers":"result-dokument"})
        url = f"https://www.buergerschaft-hh.de/{res.a['href']}"
        
    return url, filename

for wp in WPS:
    os.makedirs(f"data/{BUNDESLAND}/pdf", exist_ok=True)
    for n in tqdm(range(1,200)):
        try:
            url, filename = format_url_filename(wp, n)
            ## Sleep is needed for HH not to get blocked due to excessive requests
            time.sleep(randrange(4,8))
            # Download if PDF doesn't already exist
            if not os.path.exists(filename):
                print(url)
                urllib.request.urlretrieve(url, filename)
                
                ## Sleep is needed for HH not to get blocked due to excessive requests
                time.sleep(10)
                
        except Exception as e:
            print(e)
            print("N: ", n)
            print("--------------------------")
            time.sleep(5)
            break
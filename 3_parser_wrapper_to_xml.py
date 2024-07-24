import os
from tqdm import tqdm
import sys
import time
import subprocess

def converts_pdf_to_text(BUNDESLAND):
    """
    converts pdf files in folder data/BUNDESLAND/pdf to xml (in a separate folder)
    
    Keyword arguments:
    BUNDESLAND: "HH", "SN", "NRW" were tested
    """

    DATA_PATH = f"data/{BUNDESLAND}/pdf"
    os.makedirs(f"data/{BUNDESLAND}/xml", exist_ok=True)
    
    filenames = [os.path.join(dp, f) for dp, dn, fn in os.walk(DATA_PATH) for f in fn if f.endswith('.pdf')]
    filenames = {f: f.replace("/pdf", "/xml").replace('.pdf', '.xml') for f in filenames}
    _ = {}
    
    # Only process pdfs that haven't been converted yet
    for fi, fo in filenames.items():
        if not os.path.exists(fo):
            _[fi] = fo
    filenames = _
        
    
    for filein, fileout in (pbar := tqdm(filenames.items())):
        pbar.set_description(f"Processing {filein}\n")
        if not os.path.exists(fileout):
            try:
                subprocess.run(["python", "../venv/bin/pdf2txt.py", filein, "--char-margin", "3", "-o", fileout])
            except KeyboardInterrupt:
                # Cleanup if keyboard interrupt
                os.remove(fileout)
                sys.exit()


if __name__ == "__main__":
    
    converts_pdf_to_text("HH")
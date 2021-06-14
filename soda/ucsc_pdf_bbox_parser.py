#!/usr/bin/env python                                                                                                                                                                                                                                                     

"""ucsc-pdf-bbox-parser.py

ucsc-pdf-bbox-parser is a Python script that returns the first
bounding box ("bbox") found among the LTRect objects that are embedded 
in the PDF output of a UCSC browser snapshot. This first object's bounds
define the coordinates of the rectangle that divides the track labels 
from the track annotations, and can be used to calculate the correct
offset for a midpoint or window annotation watermark created by soda.py.

This script has been tested with the following version of pdfminer:

$ pip freeze | grep pdfminer
pdfminer==20140328

Note that other versions may have a different API that will cause 
problems with this utility.

"""

import sys
from pdfminer.pdfparser import PDFParser
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfpage import PDFPage
from pdfminer.pdfpage import PDFTextExtractionNotAllowed
from pdfminer.pdfinterp import PDFResourceManager
from pdfminer.pdfinterp import PDFPageInterpreter
from pdfminer.pdfdevice import PDFDevice
from pdfminer.layout import LAParams, LTFigure, LTCurve, LTRect
from pdfminer.converter import PDFPageAggregator

g_fn = None
g_bbox = None

def parse_lt_objs (lt_objs, page_number, found_rect, text=[]):
    """
    Iterate through the list of LT* objects 
    one level deep, and capture the data contained 
    in each. If we found what we're looking for, we
    keep going until the iterator content is exhausted.
    """
    content = []
    for lt_obj in lt_objs:
        if isinstance(lt_obj, LTRect) and not found_rect:
            content.append(lt_obj.bbox)
            found_rect = True
        elif isinstance(lt_obj, LTFigure) and not found_rect:
            # LTFigure objects are containers for other LT* objects, so recurse through the children
            content.extend(parse_lt_objs(lt_obj, page_number, found_rect, content))
    return content

def set_bbox(b=None):
    global g_bbox
    g_bbox = b

def get_bbox():
    return g_bbox
    
def set_fn(f=None):
    global g_fn
    g_fn = sys.argv[1] if not f else f

def get_fn():
    return g_fn

def main():
    set_fn(sys.argv[1])
    parse(True)
    
def parse(debug=False):
    fp = open(get_fn(), 'rb')
    parser = PDFParser(fp)
    doc = PDFDocument(parser, None)
    if not doc.is_extractable:
        raise PDFTextExtractionNotAllowed
    rsrcmgr = PDFResourceManager()
    laparams = LAParams()
    device = PDFPageAggregator(rsrcmgr, laparams=laparams)
    interpreter = PDFPageInterpreter(rsrcmgr, device)
    
    content = []
    for i, page in enumerate(PDFPage.create_pages(doc)):
        interpreter.process_page(page)
        layout = device.get_result()
        content.extend(parse_lt_objs(layout, (i+1), False))

    set_bbox(content[0])
    
    # print first LTLine object bbox tuple
    if debug: 
        sys.stderr.write("First LTRect bbox in PDF -> %s\n" % (get_bbox(),))

if __name__ == "__main__":
    main()

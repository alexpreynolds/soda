#!/usr/bin/env python

"""soda.py

soda.py is a Python script that generates a gallery of images made from snapshots 
from a UCSC genome browser instance, so-called "soda plots". Snapshots could be 
derived from the Altius internal browser instance gb1, or any other UCSC browser 
instance, if specified.

You provide the script with four parameters:

* A BED-formatted file containing your regions of interest.
* The genome build name ('hg19', 'mm9', etc.)
* The session ID from your genome browser session, which specifies the browser 
  tracks you want to visualize, as well as other visual display parameters that 
  are specific to your session. 
* Where you want to store the gallery end-product.

Additional options are available. Run with --help for more information or read 
the Options section of the README at: https://github.com/Altius/soda#options

"""

import sys
import os
import tempfile
import shutil
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import requests_kerberos
import certifi
import optparse
import urllib
import json
import bs4
import re
import subprocess
import jinja2
import pdfrw
import soda.ucsc_pdf_bbox_parser
import time
import datetime

default_title = "Soda Gallery"
default_genome_browser_url = "https://genome.ucsc.edu"
default_genome_browser_username = None
default_genome_browser_password = None
default_verbosity = False
default_use_kerberos_authentication = False
default_midpoint_annotation = False
default_interval_annotation = False
default_annotation_rgba = "rgba(255, 0, 0, 0.333)" # i.e., full red with 33% opacity
default_annotation_font_size = "5.5"
default_annotation_font_family = "Helvetica"
default_output_png_resolution = 150
default_output_png_thumbnail_width = 480
default_output_png_thumbnail_height = 480
default_annotation_resolution = default_output_png_resolution
default_ucsc_browser_label_area_width = 17
default_ucsc_browser_text_size = 8
default_gallery_mode = 'photoswipe'

parser = optparse.OptionParser()
parser.add_option("-r", "--regionsFn", action="store", type="string", dest="regionsFn", help="Path to BED-formatted regions of interest (required)")
parser.add_option("-s", "--browserSessionID", action="store", type="string", dest="browserSessionID", help="Genome browser session ID (required)")
parser.add_option("-o", "--outputDir", action="store", type="string", dest="outputDir", help="Output gallery directory (required)")
parser.add_option("-b", "--browserBuildID", action="store", type="string", dest="browserBuildID", help="Genome build ID (required)")
parser.add_option("-t", "--galleryTitle", action="store", type="string", dest="galleryTitle", default=default_title, help="Gallery title (optional)")
parser.add_option("-g", "--browserURL", action="store", type="string", dest="browserURL", default=default_genome_browser_url, help="Genome browser URL (optional)")
parser.add_option("-u", "--browserUsername", action="store", type="string", dest="browserUsername", default=default_genome_browser_username, help="Genome browser username (optional)")
parser.add_option("-p", "--browserPassword", action="store", type="string", dest="browserPassword", default=default_genome_browser_password, help="Genome browser password (optional)")
parser.add_option("-y", "--useKerberosAuthentication", action="store_true", dest="useKerberosAuthentication", default=default_use_kerberos_authentication, help="Use Kerberos authentication (optional)")
parser.add_option("-d", "--addMidpointAnnotation", action="store_true", dest="midpointAnnotation", default=default_midpoint_annotation, help="Add midpoint annotation underneath tracks (optional)")
parser.add_option("-i", "--addIntervalAnnotation", action="store_true", dest="intervalAnnotation", default=default_interval_annotation, help="Add interval annotation underneath tracks (optional)")
parser.add_option("-w", "--annotationRgba", action="store", type="string", dest="annotationRgba", default=default_annotation_rgba, help="Annotation 'rgba(r,g,b,a)' color string (optional)")
parser.add_option("-z", "--annotationFontPointSize", action="store", type="string", dest="annotationFontPointSize", default=default_annotation_font_size, help="Annotation font point size (optional)")
parser.add_option("-f", "--annotationFontFamily", action="store", type="string", dest="annotationFontFamily", default=default_annotation_font_family, help="Annotation font family (optional)")
parser.add_option("-e", "--annotationResolution", action="store", type="string", dest="annotationResolution", default=default_annotation_resolution, help="Annotation resolution, dpi (optional)")
parser.add_option("-j", "--outputPngResolution", action="store", type="string", dest="outputPngResolution", default=default_output_png_resolution, help="Output PNG resolution, dpi (optional)")
parser.add_option("-a", "--range", action="store", type="int", dest="rangePadding", help="Add or remove symmetrical padding to input regions (optional)")
parser.add_option("-l", "--gallerySrcDir", action="store", type="string", dest="gallerySrcDir", help="Gallery resources directory (optional)")
parser.add_option("-c", "--octiconsSrcDir", action="store", type="string", dest="octiconsSrcDir", help="Github Octicons resources directory (optional)")
parser.add_option("-k", "--convertBinFn", action="store", type="string", dest="convertBinFn", help="ImageMagick convert binary path (optional)")
parser.add_option("-n", "--identifyBinFn", action="store", type="string", dest="identifyBinFn", help="ImageMagick identify binary path (optional)")
parser.add_option("-m", "--galleryMode", dest="galleryMode", default="photoswipe", help="Gallery mode: blueimp or photoswipe [default: %default]")
parser.add_option("-v", "--verbose", action="store_true", dest="verbose", default=default_verbosity, help="Print debug messages to stderr (optional)")
(options, args) = parser.parse_args()

def usage(errCode):
    args = ["-h"]
    (options, args) = parser.parse_args(args)
    sys.exit(errCode)

default_requests_max_retries = 5
default_requests_backoff_factor = 10  # sleep for [0.0s, 10s, 20s, ...] between retries
default_requests_status_forcelist = [ 500, 502, 503, 504 ]

def create_retriable_session():
    session = requests.Session()
    retries = Retry(
        total = default_requests_max_retries,
        backoff_factor = default_requests_backoff_factor,
        status_forcelist = default_requests_status_forcelist,
    )
    session.mount('http://', HTTPAdapter(max_retries=retries))
    session.mount('https://', HTTPAdapter(max_retries=retries))
    return session

class Soda:
    def __init__(self):
        self.temp_results_dir = None
        self.temp_regions_results_dir = None
        self.temp_pdf_results_dir = None
        self.temp_png_results_dir = None
        self.temp_thumb_results_dir = None
        self.output_dir = None
        self.output_regions_dir = None
        self.output_pdf_dir = None
        self.output_png_dir = None
        self.original_regions_fn = None
        self.octicons_resources_dir = None
        self.gallery_resources_dir = None
        self.gallery_title = None
        self.temp_regions_fn = None
        self.temp_annotated_regions_fn = None
        self.temp_annotated_regions_fh = None
        self.browser_url = None
        self.browser_dump_url = None
        self.browser_pdf_url = None
        self.browser_session_id = None
        self.browser_session_kerberos_credentials = False
        self.browser_session_basic_credentials = False
        self.browser_session_username = None
        self.browser_session_password = None
        self.browser_build_id = None
        self.region_ids = []
        self.region_objs = []
        self.range_padding = None
        self.convert_bin_fn = None
        self.identify_bin_fn = None
        self.output_png_resolution = default_output_png_resolution
        self.output_png_thumbnail_width = default_output_png_thumbnail_width
        self.output_png_thumbnail_height = default_output_png_thumbnail_height
        self.midpoint_annotation = default_midpoint_annotation
        self.interval_annotation = default_interval_annotation
        self.annotation_rgba = default_annotation_rgba
        self.annotation_font_family = default_annotation_font_family
        self.annotation_resolution = default_annotation_resolution
        self.track_label_column_width = None
        self.gallery_mode = default_gallery_mode

    def setup_midpoint_annotation(this, midpointAnnotation, debug):
        this.midpoint_annotation = midpointAnnotation
        if debug:
            if this.midpoint_annotation:
                sys.stderr.write("Debug: Midpoint annotation enabled\n")
            else:
                sys.stderr.write("Debug: Midpoint annotation disabled\n")

    def setup_interval_annotation(this, intervalAnnotation, debug):
        this.interval_annotation = intervalAnnotation
        if debug:
            if this.interval_annotation:
                sys.stderr.write("Debug: Interval annotation enabled\n")
            else:
                sys.stderr.write("Debug: Interval annotation disabled\n")

    def setup_annotation_rgba(this, annotationRgba, debug):
        this.annotation_rgba = annotationRgba
        if debug:
            sys.stderr.write("Debug: Annotation RGBA color string set to [%s]\n" % (this.annotation_rgba))

    def setup_annotation_font_point_size(this, annotationFontPointSize, debug):
        this.annotation_font_point_size = annotationFontPointSize
        if debug:
            sys.stderr.write("Debug: Annotation font point size string set to [%s]\n" % (this.annotation_font_point_size))

    def setup_annotation_font_family(this, annotationFontFamily, debug):
        this.annotation_font_family = annotationFontFamily
        if debug:
            sys.stderr.write("Debug: Annotation font family set to [%s]\n" % (this.annotation_font_family))

    def setup_annotation_resolution(this, annotationResolution, debug):
        this.annotation_resolution = int(annotationResolution)
        if debug:
            sys.stderr.write("Debug: Annotation resolution string set to [%s]\n" % (this.annotation_resolution))

    def setup_output_png_resolution(this, outputPngResolution, debug):
        this.output_png_resolution = int(outputPngResolution)
        if debug:
            sys.stderr.write("Debug: Output PNG resolution string set to [%s]\n" % (this.output_png_resolution))

    def setup_range_padding(this, rangePadding, debug):
        this.range_padding = rangePadding
        if debug:
            sys.stderr.write("Debug: Set range padding value to [%i]\n" % (this.range_padding))
        
    def setup_temp_dirs(this, debug):
        this.temp_results_dir = tempfile.mkdtemp()
        if debug:
            sys.stderr.write("Debug: Created temp results dir [%s]\n" % (this.temp_results_dir))
        this.temp_regions_results_dir = os.path.join(this.temp_results_dir, 'regions')
        os.makedirs(this.temp_regions_results_dir)
        if debug:
            sys.stderr.write("Debug: Created temp regions results dir [%s]\n" % (this.temp_regions_results_dir))
        this.temp_pdf_results_dir = os.path.join(this.temp_results_dir, 'pdfs')
        os.makedirs(this.temp_pdf_results_dir)
        if debug:
            sys.stderr.write("Debug: Created temp PDF results dir [%s]\n" % (this.temp_pdf_results_dir))
        this.temp_png_results_dir = os.path.join(this.temp_results_dir, 'images')
        os.makedirs(this.temp_png_results_dir)
        if debug:
            sys.stderr.write("Debug: Created temp PNG results dir [%s]\n" % (this.temp_png_results_dir))
        this.temp_thumbs_results_dir = os.path.join(this.temp_png_results_dir, 'thumbnails')
        os.makedirs(this.temp_thumbs_results_dir)
        if debug:
            sys.stderr.write("Debug: Created temp thumbnails results dir [%s]\n" % (this.temp_thumbs_results_dir))
            
    def breakdown_temp_dir(this, debug):
        if this.temp_results_dir:
            if debug:
                sys.stderr.write("Debug: Removing temp results dir [%s]\n" % (this.temp_results_dir))
            shutil.rmtree(this.temp_results_dir)
            this.temp_results_dir = None
        else:
            sys.stderr.write("Error: Could not remove temp dir [%s]\n\n" % (this.temp_results_dir))
            usage(-1)
            
    def setup_output_dir(this, outputDir, debug):
        if os.path.exists(outputDir):
            sys.stderr.write("Error: Path %s exists -- remove or rename before re-running script\n\n" % (outputDir))
            usage(-1)
        else:
            os.makedirs(outputDir)
            this.output_dir = outputDir
            if debug:
                sys.stderr.write("Debug: Created final results dir [%s]\n" % (this.output_dir))
            
    def ensure_regions_fn(this, regionsFn, debug):
        if not os.path.exists(regionsFn):
            sys.stderr.write("Error: Regions file [%s] is not accessible\n\n" % (regionsFn))
            usage(-1)
        else:
            this.original_regions_fn = regionsFn
            if debug:
                sys.stderr.write("Debug: Regions file exists [%s]\n" % (this.original_regions_fn))

    def ensure_gallery_src_dir(this, gallerySrcDir, debug):
        if not os.path.exists(gallerySrcDir):
            sys.stderr.write("Error: Gallery resources directory [%s] is not accessible\n\n" % (gallerySrcDir))
            usage(-1)
        else:
            this.gallery_resources_dir = gallerySrcDir
            if debug:
                sys.stderr.write("Debug: Gallery resources directory exists [%s]\n" % (this.gallery_resources_dir))

    def ensure_octicons_src_dir(this, octiconsSrcDir, debug):
        if not os.path.exists(octiconsSrcDir):
            sys.stderr.write("Error: Github Octicons resources directory [%s] is not accessible\n\n" % (octiconsSrcDir))
            usage(-1)
        else:
            this.octicons_resources_dir = octiconsSrcDir
            if debug:
                sys.stderr.write("Debug: Github Octicons resources directory exists [%s]\n" % (this.octicons_resources_dir))                
    
    def ensure_convert_bin_fn(this, convertBinFn, debug):
        if not convertBinFn:
            sys.stderr.write("Error: ImageMagick convert binary not found\n\n")
            usage(-1)
        elif not os.path.exists(convertBinFn):
            sys.stderr.write("Error: ImageMagick convert binary path [%s] is not accessible\n\n" % (convertBinFn))
            usage(-1)
        else:
            this.convert_bin_fn = convertBinFn
            if debug:
                sys.stderr.write("Debug: Convert binary path exists [%s]\n" % (this.convert_bin_fn))

    def find_convert_bin_fn_in_environment_path(this, debug):
        convertBinName = 'convert'
        env = os.environ.copy()
        paths_to_search = env['PATH'].split(":")
        for path in paths_to_search:
            for root, dirs, files in os.walk(path):
                if convertBinName in files:
                    return os.path.join(root, convertBinName)
        return None

    def ensure_identify_bin_fn(this, identifyBinFn, debug):
        if not identifyBinFn:
            sys.stderr.write("Error: ImageMagick identify binary not found\n\n")
            usage(-1)
        elif not os.path.exists(identifyBinFn):
            sys.stderr.write("Error: ImageMagick identify binary path [%s] is not accessible\n\n" % (identifyBinFn))
            usage(-1)
        else:
            this.identify_bin_fn = identifyBinFn
            if debug:
                sys.stderr.write("Debug: Identify binary path exists [%s]\n" % (this.identify_bin_fn))

    def find_identify_bin_fn_in_environment_path(this, debug):
        identifyBinName = 'identify'
        env = os.environ.copy()
        paths_to_search = env['PATH'].split(":")
        for path in paths_to_search:
            for root, dirs, files in os.walk(path):
                if identifyBinName in files:
                    return os.path.join(root, identifyBinName)
        return None

    def copy_regions_to_temp_regions_dir(this, debug):
        this.temp_regions_fn = os.path.join(this.temp_regions_results_dir, os.path.basename(this.original_regions_fn))
        shutil.copyfile(this.original_regions_fn, this.temp_regions_fn)
        if debug:
            sys.stderr.write("Debug: Copied [%s] to [%s]\n" % (this.original_regions_fn, this.temp_regions_fn))

    def annotate_temp_regions_with_custom_id(this, debug):
        this.temp_annotated_regions_fn = this.temp_regions_fn + ".annotated"
        this.temp_annotated_regions_fh = open(this.temp_annotated_regions_fn, "w")
        with open(this.temp_regions_fn, "r") as region_fh:
            counter = 0
            zero_padding = 6
            for region_line in region_fh:
                region_elements = region_line.rstrip().split('\t')
                original_start = region_elements[1]
                original_stop = region_elements[2]      
                annotation_id = None
                # skip if blank line
                if len(region_elements) == 1:
                    sys.stderr.write("Warning: Possible blank line in input regions file\n")
                    continue
                # skip if start and stop are the same
                if int(original_start) == int(original_stop):
                    sys.stderr.write("Warning: Possible zero-length region in input regions file\n")
                    continue
                # adjust range, if set
                if this.range_padding:
                    try:
                        midpoint = int(region_elements[1]) + ((int(region_elements[2]) - int(region_elements[1])) / 2)
                        region_elements[1] = str(int(midpoint) - this.range_padding)
                        region_elements[2] = str(int(midpoint) + this.range_padding)
                        #region_elements[1] = str(int(region_elements[1]) - this.range_padding)
                        #region_elements[2] = str(int(region_elements[2]) + this.range_padding)
                        if int(region_elements[1]) < 0:
                            region_elements[1] = '0'
                    except IndexError as ie:
                        sys.stderr.write("Error: Region elements are [%d | %s]\n" % (len(region_elements), region_elements))
                        sys.exit(-1)
                # create modified ID from index, position and current ID, if available
                # re-encode in ASCII character set (with risk of data loss) to avoid template rendering errors
                if len(region_elements) >= 4:
                    mod_id = ""
                    try:
                        mod_id = region_elements[3].decode("utf-8").encode("ascii", "ignore")
                        mod_id = mod_id.replace(' ', '-')
                        mod_id = mod_id.replace(':', '-')
                        mod_id = mod_id.replace('_', '-')
                    except AttributeError as err:
                        mod_id = region_elements[3]
                        mod_id = mod_id.replace(' ', '-')
                        mod_id = mod_id.replace(':', '-')
                        mod_id = mod_id.replace('_', '-')
                    annotation_id = "_".join(['plot', str(counter).zfill(zero_padding), region_elements[0], region_elements[1], region_elements[2], mod_id])
                elif len(region_elements) == 3:
                    annotation_id = "_".join(['plot', str(counter).zfill(zero_padding), region_elements[0], region_elements[1], region_elements[2]])
                if annotation_id:
                    annotated_line = '\t'.join([region_elements[0], region_elements[1], region_elements[2], annotation_id, original_start, original_stop]) + '\n'
                    this.temp_annotated_regions_fh.write(annotated_line)
                counter = counter + 1
        if debug:
            sys.stderr.write("Debug: Annotated regions file written to [%s]\n" % (this.temp_annotated_regions_fn))  
        this.temp_annotated_regions_fh.close()

    def setup_browser_url(this, browserURL, debug):
        this.browser_url = browserURL
        if debug:
            sys.stderr.write("Debug: Browser URL set to [%s]\n" % (this.browser_url))
        
    def setup_browser_username(this, browserUsername, debug):
        this.browser_username = browserUsername
        if debug:
            sys.stderr.write("Debug: Browser username set to [%s]\n" % (this.browser_username))

    def setup_browser_password(this, browserPassword, debug):
        this.browser_password = browserPassword
        if debug:
            sys.stderr.write("Debug: Browser password set to [%s]\n" % (this.browser_password))

    def setup_browser_authentication_type(this, useKerberosCredentials, debug):
        if debug:
            sys.stderr.write("Debug: useKerberosCredentials set to [%r]\n" % (useKerberosCredentials))
        if this.browser_username and this.browser_password:
            this.browser_session_basic_credentials = True
            this.browser_session_kerberos_credentials = False
        if useKerberosCredentials:
            this.browser_session_basic_credentials = False
            this.browser_session_kerberos_credentials = True
        if debug:
            sys.stderr.write("Debug: Basic credentials set to [%r]\n" % (this.browser_session_basic_credentials))
            sys.stderr.write("Debug: Kerberos credentials set to [%r]\n" % (this.browser_session_kerberos_credentials))

    def setup_browser_build_id(this, browserBuildID, debug):
        this.browser_build_id = browserBuildID
        if debug:
            sys.stderr.write("Debug: Browser build ID set to [%s]\n" % (this.browser_build_id))

    def setup_browser_dump_url(this, debug):
        this.browser_dump_url = this.browser_url + '/cgi-bin/cartDump?cartDumpAsTable=[]'
        if debug:
            sys.stderr.write("Debug: Browser dump URL set to [%s]\n" % (this.browser_dump_url))

    def setup_browser_pdf_url(this, debug):
        this.browser_pdf_url = this.browser_url + '/cgi-bin/hgTracks?hgsid=' + this.browser_session_id + '&hgt.psOutput=on&db=' + this.browser_build_id
        if debug:
            sys.stderr.write("Debug: Browser PDF URL set to [%s]\n" % (this.browser_pdf_url))

    def setup_browser_session_id(this, browserSessionID, debug):
        this.browser_session_id = browserSessionID
        if debug:
            sys.stderr.write("Debug: Browser session ID set to [%s]\n" % (this.browser_session_id))

    def generate_pdfs_from_annotated_regions(this, debug):
        with open(this.temp_annotated_regions_fn, "r") as temp_annotated_regions_fh:
            for region_line in temp_annotated_regions_fh:
                region_elements = region_line.rstrip().split('\t')
                region_obj = {
                    u"chrom"    : region_elements[0],
                    u"start"    : region_elements[1],
                    u"stop"     : region_elements[2],
                    u"id"       : region_elements[3],
                    u"o_start"  : region_elements[4],
                    u"o_stop"   : region_elements[5]
                }
                region_id = region_obj['id']
                this.region_objs.append(region_obj)
                this.generate_pdf_from_annotated_region(region_obj, region_id, debug)
    
    def generate_pdf_url_response(this, pdf_url, credentials, enc_position_str):
        try:
            s = create_retriable_session()
            browser_pdf_url_response = s.get(
                url = pdf_url,
                auth = credentials,
                verify = True,
            )
            return browser_pdf_url_response.text
        except requests.exceptions.ChunkedEncodingError as err:
            sys.stderr.write("Warning: Could not retrieve PDF for region [%s]\n" % (enc_position_str))
            return None
    
    def generate_pdf_hrefs(this, response_text, debug):
        browser_pdf_url_soup = bs4.BeautifulSoup(response_text, "html.parser")
        browser_pdf_url_soup_hrefs = []
        for anchor in browser_pdf_url_soup.find_all('a'):
            browser_pdf_url_soup_hrefs.append(anchor['href'])
        if debug:
            sys.stderr.write("Debug: Unfiltered PDF soup anchor HREFs are [%s]\n" % (str(browser_pdf_url_soup_hrefs)))        
        browser_pdf_url_regex = re.compile("hgt_[a-z0-9_]*.pdf")
        browser_pdf_url_soup_hrefs_filtered = [href for href in browser_pdf_url_soup_hrefs if browser_pdf_url_regex.search(href)]
        if debug:
            sys.stderr.write("Debug: Filtered PDF soup anchor HREFs are [%s]\n" % (str(browser_pdf_url_soup_hrefs_filtered)))
        browser_pdf_url_soup_hrefs_converted = [href.replace('..', this.browser_url) for href in browser_pdf_url_soup_hrefs_filtered]
        if debug:
            sys.stderr.write("Debug: Converted PDF soup anchor HREFs are [%s]\n" % (str(browser_pdf_url_soup_hrefs_converted)))
        return browser_pdf_url_soup_hrefs_converted

    def generate_pdf_from_annotated_region(this, region_obj, region_id, debug):
        browser_position_str = region_obj['chrom'] + ":" + str(region_obj['start']) + "-" + str(region_obj['stop'])
        browser_post_body = {
            u"hgsid"             : this.browser_session_id,
            u"hgt.psOutput"      : u"on",
            u"cartDump.varName"  : u"position",
            u"cartDump.newValue" : browser_position_str,
            u"submit"            : u"submit"
        }
        if debug:
            sys.stderr.write("Debug: Submitting POST body [%s] to request\n" % (browser_post_body))
        browser_credentials = None
        if this.browser_session_basic_credentials:
            browser_credentials = requests.auth.HTTPBasicAuth(this.browser_username, this.browser_password)
        elif this.browser_session_kerberos_credentials:
            browser_credentials = requests_kerberos.HTTPKerberosAuth(mutual_authentication=requests_kerberos.OPTIONAL)
        browser_cartdump_response = requests.post(
            url = this.browser_dump_url,
            data = browser_post_body,
            auth = browser_credentials,
            verify = True,
        )
        if debug:
            sys.stderr.write("Debug: Credentials [%s]\n" % (str(browser_credentials)))
        if browser_cartdump_response.status_code == 401:
            sys.stderr.write("Error: No credentials available -- please use 'kinit' to set up a Kerberos ticket, or specify a Basic username and password\n")
            sys.exit(-1)
        elif browser_cartdump_response.status_code != 200:
            sys.stderr.write("Error: Access to genome browser failed\nStatus\t[%d]\nHeaders\t[%s]\nText\t[%s]" % (browser_cartdump_response.status_code, browser_cartdump_response.headers, browser_cartdump_response.text))
            sys.exit(-1)
        # get cart dump
        browser_cartdump_response_content = browser_cartdump_response.content
        browser_cartdump_textSize = None # textSize
        browser_cartdump_hgt_labelWidth = None # hgt.labelWidth
        browser_cartdump_lines = []
        try:
            browser_cartdump_lines = browser_cartdump_response_content.split('\n')
        except TypeError as te:
            browser_cartdump_lines = browser_cartdump_response_content.decode().split('\n')
        for browser_cartdump_line in browser_cartdump_lines:
            try:
                browser_cartdump_line_values = browser_cartdump_line.rstrip().split(' ')
                if debug:
                    sys.stderr.write("Debug: Cart dump lines: [%s]\n" % (browser_cartdump_line_values))
            except ValueError as ve:
                sys.stderr.write("Error: Could not parse cartDump response [%s]" % (browser_cartdump_response_content))
                sys.exit(-1)
            if browser_cartdump_line_values[0] == 'textSize':
                browser_cartdump_textSize = browser_cartdump_line_values[1]
            elif browser_cartdump_line_values[0] == 'hgt.labelWidth':
                browser_cartdump_hgt_labelWidth = browser_cartdump_line_values[1]
        if browser_cartdump_textSize is None:
            browser_cartdump_textSize = default_ucsc_browser_text_size
        if browser_cartdump_hgt_labelWidth is None:
            browser_cartdump_hgt_labelWidth = default_ucsc_browser_label_area_width
        if debug:
            sys.stderr.write("Debug: Cart dump textSize and hgt.labelWidth are: [%s] and [%s]\n" % (browser_cartdump_textSize, browser_cartdump_hgt_labelWidth))

        # write response text to cartDump in temporary output folder
        cart_dump_fn = os.path.join(this.temp_pdf_results_dir, 'cartDump')
        if debug:
            sys.stderr.write("Debug: Writing cart dump response content to [%s]\n" % (cart_dump_fn))
        cart_dump_fh = open(cart_dump_fn, "w")
        try:
            cart_dump_fh.write(browser_cartdump_response_content)
        except TypeError as te:
            cart_dump_fh.write(browser_cartdump_response_content.decode())
        cart_dump_fh.close()
        # ensure cartDump exists
        if not os.path.exists(cart_dump_fn):
            sys.stderr.write("Error: Could not write cart dump data to [%s]\n" % (cart_dump_fn))
            sys.exit(-1)
        # get PDF URL
        encoded_browser_position_str = region_obj['chrom'] + "%3A" + str(region_obj['start']) + "%2D" + str(region_obj['stop'])        
        modified_browser_pdf_url = this.browser_pdf_url + "&position=" + encoded_browser_position_str
        if debug:
            sys.stderr.write("Debug: Requesting PDF via: [%s]\n" % (modified_browser_pdf_url))
        convert_attempt_counter = 0
        request_attempt_counter = 0
        browser_pdf_url_soup_hrefs_converted = []
        while True:
            browser_pdf_url_response_text = None
            while True:
                browser_pdf_url_response_text = this.generate_pdf_url_response(modified_browser_pdf_url, browser_credentials, encoded_browser_position_str)
                if browser_pdf_url_response_text:
                    break
                request_attempt_counter += 1
                if request_attempt_counter == 5:
                    sys.stderr.write("Error: Could not successfully retrieve complete cart response")
                    usage(-1)
            browser_pdf_url_soup_hrefs_converted = this.generate_pdf_hrefs(browser_pdf_url_response_text, debug)
            if len(browser_pdf_url_soup_hrefs_converted) == 1:
                break
            convert_attempt_counter += 1
            if convert_attempt_counter == 5:
                sys.stderr.write("Error: No or more than one PDF available for this region\n")
                usage(-1)
        browser_pdf_url = browser_pdf_url_soup_hrefs_converted[0]
        browser_pdf_response = requests.get(
            url = browser_pdf_url,
            stream = True,
            auth = browser_credentials,
            verify = True,
        )
        browser_pdf_local_fn = os.path.join(this.temp_pdf_results_dir, region_obj['id'] + '.pdf')
        with open(browser_pdf_local_fn, 'wb') as browser_pdf_local_fh:
            for chunk in browser_pdf_response.iter_content(chunk_size = 1024):
                if chunk:
                    browser_pdf_local_fh.write(chunk)
        if debug:
            sys.stderr.write("Debug: Wrote PDF file [%s]\n" % (browser_pdf_local_fn))
        # remove cartDump file
        os.remove(cart_dump_fn)
        if this.midpoint_annotation or this.interval_annotation:
            # set the track_label_column_width based on the bounding box calculation
            ucsc_pdf_bbox_parser.set_fn(browser_pdf_local_fn)
            ucsc_pdf_bbox_parser.parse(debug)
            bbox_x_l = ucsc_pdf_bbox_parser.get_bbox()[0]
            bbox_x_r = ucsc_pdf_bbox_parser.get_bbox()[2]
            this.track_label_column_width = bbox_x_r - ((bbox_x_r - bbox_x_l) / 2) + 1
            this.generate_pdf_with_annotation(browser_pdf_local_fn, region_obj, debug)
        this.region_ids.append(region_id)

    def generate_pdf_with_annotation(this, browser_pdf_local_fn, region_obj, debug):
        # get dimensions of browser PDF with 'identify'
        identify_width_cmd = '%s -ping -format \'%%w\' %s' % (this.identify_bin_fn, browser_pdf_local_fn)
        try:
            browser_pdf_width = subprocess.check_output(identify_width_cmd, shell = True)
        except subprocess.CalledProcessError as err:
            identify_width_result = "Error: Command '{}' returned with error (code {}): {}".format(err.cmd, err.returncode, err.output)
            sys.stderr.write("%s\n" % (identify_width_result))
            sys.exit(-1)
        if debug:
            sys.stderr.write("Debug: PDF width [%s]\n" % (browser_pdf_width))
        identify_height_cmd = '%s -ping -format \'%%h\' %s' % (this.identify_bin_fn, browser_pdf_local_fn)
        try:
            browser_pdf_height = subprocess.check_output(identify_height_cmd, shell = True)
        except subprocess.CalledProcessError as err:
            identify_height_result = "Error: Command '{}' returned with error (code {}): {}".format(err.cmd, err.returncode, err.output)
            sys.stderr.write("%s\n" % (identify_height_result))
            sys.exit(-1)
        if debug:
            sys.stderr.write("Debug: PDF height [%s]\n" % (browser_pdf_height))
        # make blank SVG with similar dimensions (same width, but taller)
        top_padding = 20
        leftmost_column_width = this.track_label_column_width
        track_column_width = int(browser_pdf_width) - leftmost_column_width
        svg = '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="%d" height="%d" viewBox="0 0 %d %d">' % (int(browser_pdf_width), int(browser_pdf_height) + top_padding, int(browser_pdf_width), int(browser_pdf_height) + top_padding)
        if this.midpoint_annotation:
            # draw <line> on SVG
            svg_line_x1 = leftmost_column_width + (track_column_width / 2.0)
            svg_line_x2 = svg_line_x1
            svg_line_y1 = 0 
            svg_line_y2 = int(browser_pdf_height) + top_padding
            svg_line_stroke = this.annotation_rgba
            svg_line_stroke_width = '0.25'
            svg_line_fill = 'none'
            svg = svg + '<line x1="%d" y1="%d" x2="%d" y2="%d" style="stroke:%s;stroke-width:%s;fill:%s;" />' % (svg_line_x1, svg_line_y1, svg_line_x2, svg_line_y2, svg_line_stroke, svg_line_stroke_width, svg_line_fill)
            # draw <text> on SVG
            svg_text_chr = region_obj['chrom']
            svg_text_start = int(region_obj['start']) + int((int(region_obj['stop']) - int(region_obj['start'])) / 2)
            svg_text_stop = svg_text_start + 1
            svg_text = '%s:%d-%d' % (svg_text_chr, svg_text_start, svg_text_stop)
            svg_text_x = svg_line_x1 + 3
            svg_text_y = 8
            svg_text_fill = svg_line_stroke
            svg_text_font_family = this.annotation_font_family
            svg_text_font_size = this.annotation_font_point_size
            svg = svg + '<text x="%d" y="%d" style="font-family:%s;fill:%s;font-size:%s">%s</text>' % (svg_text_x, svg_text_y, svg_text_font_family, svg_text_fill, svg_text_font_size, svg_text)
        elif this.interval_annotation:
            # draw <rect> element on SVG
            full_start = region_obj['start']
            full_stop = region_obj['stop']
            original_start = region_obj['o_start']
            original_stop = region_obj['o_stop']
            rect_width_in_bases = float(original_stop) - float(original_start)
            column_width_in_bases = float(2.0 * this.range_padding)
            ratio_of_rect_width_to_column_width = rect_width_in_bases / column_width_in_bases
            rect_width_in_pixels = track_column_width * ratio_of_rect_width_to_column_width
            column_rect_width_difference = track_column_width - rect_width_in_pixels
            column_rect_offset = column_rect_width_difference / 2.0
            adj_track_column_width = rect_width_in_pixels
            adj_track_column_height = int(browser_pdf_height) + top_padding
            svg_rect_x = leftmost_column_width + column_rect_offset
            svg_rect_y = 0
            svg_rect_width = adj_track_column_width
            svg_rect_height = adj_track_column_height
            svg_rect_fill = this.annotation_rgba
            svg_rect_stroke = svg_rect_fill
            svg_rect_stroke_width = '0'
            svg = svg + '<rect x="%d" y="%d" width="%d" height="%d" style="fill:%s;stroke-width:%s;stroke:%s" />' % (svg_rect_x, svg_rect_y, svg_rect_width, svg_rect_height, svg_rect_fill, svg_rect_stroke_width, svg_rect_stroke)
            # draw <text> on SVG
            svg_text_chr = region_obj['chrom']
            svg_text = '%s:%d-%d' % (svg_text_chr, int(original_start), int(original_stop))
            svg_text_x = leftmost_column_width + (track_column_width / 2.0)
            svg_text_y = 8
            svg_text_fill = 'rgba(0,0,0,1)'
            svg_text_font_family = this.annotation_font_family
            svg_text_font_size = this.annotation_font_point_size
            svg_text_anchor = "middle"
            svg = svg + '<text x="%d" y="%d" text-anchor="%s" style="font-family:%s;fill:%s;font-size:%s">%s</text>' % (svg_text_x, svg_text_y, svg_text_anchor, svg_text_font_family, svg_text_fill, svg_text_font_size, svg_text)
        svg = svg + '</svg>'
        # write SVG to text file
        svg_local_fn = os.path.join(this.temp_pdf_results_dir, 'watermark.svg')
        with open(svg_local_fn, 'wb') as svg_local_fh:
            svg_local_fh.write(svg)
        if debug:
            sys.stderr.write("Debug: Written SVG watermark to [%s]\n" % (svg_local_fn))
        # `convert` SVG to PDF with specified annotation resolution
        svg_as_pdf_local_fn = os.path.join(this.temp_pdf_results_dir, 'watermark.pdf')
        convert_cmd = '%s -density %d %s -background white -flatten %s' % (this.convert_bin_fn, this.annotation_resolution, svg_local_fn, svg_as_pdf_local_fn)
        try:
            convert_result = subprocess.check_output(convert_cmd, shell = True)
        except subprocess.CalledProcessError as err:
            convert_result = "Error: Command '{}' returned with error (code {}): {}".format(err.cmd, err.returncode, err.output)
            sys.stderr.write("%s\n" % (convert_result))
            sys.exit(-1)
        if debug:
            sys.stderr.write("Debug: Converted SVG watermark to PDF\n")
        # watermark the SVG with the browser PDF, using pdfrw library
        watermarked_browser_pdf_local_fn = browser_pdf_local_fn + '.watermarked'
        browser_pdfrw_obj = pdfrw.PageMerge().add(pdfrw.PdfReader(browser_pdf_local_fn).pages[0])[0]
        svg_pdfrw_obj = pdfrw.PdfReader(svg_as_pdf_local_fn)
        for page in svg_pdfrw_obj.pages:
            pdfrw.PageMerge(page).add(browser_pdfrw_obj, prepend=False).render()
        pdfrw.PdfWriter().write(watermarked_browser_pdf_local_fn, svg_pdfrw_obj)
        if debug:
            sys.stderr.write("Debug: Merged SVG watermark with browser PDF\n")
        # copy watermarked_browser_pdf_local_fn to browser_pdf_local_fn
        shutil.copyfile(watermarked_browser_pdf_local_fn, browser_pdf_local_fn)
        # remove temporary files
        os.remove(svg_local_fn)
        os.remove(svg_as_pdf_local_fn)
        os.remove(watermarked_browser_pdf_local_fn)

    def generate_pngs_from_pdfs(this, debug):
        for region_id in this.region_ids:
            this.generate_png_from_pdf(region_id, debug)

    def generate_png_from_pdf(this, region_id, debug):
        browser_pdf_local_fn = os.path.join(this.temp_pdf_results_dir, region_id + '.pdf')
        browser_png_local_fn = os.path.join(this.temp_png_results_dir, region_id + '.png')
        # convert PDF to PNG with specified output resolution
        convert_cmd = '%s -density %d %s -background white -flatten %s' % (this.convert_bin_fn, this.output_png_resolution, browser_pdf_local_fn, browser_png_local_fn)
        try:
            convert_result = subprocess.check_output(convert_cmd, shell = True)
        except subprocess.CalledProcessError as err:
            convert_result = "Error: Command '{}' returned with error (code {}): {}".format(err.cmd, err.returncode, err.output)
            sys.stderr.write("%s\n" % (convert_result))
            sys.exit(-1)
        if debug:
            sys.stderr.write("Debug: Converted image file located at [%s]\n" % (browser_png_local_fn))

    def generate_thumbnails_from_pngs(this, debug):
        for region_id in this.region_ids:
            this.generate_thumbnail_from_png(region_id, debug)        

    def generate_thumbnail_from_png(this, region_id, debug):
        browser_png_local_fn = os.path.join(this.temp_png_results_dir, region_id + '.png')
        browser_thumb_local_fn = os.path.join(this.temp_thumbs_results_dir, region_id + '.png')
        browser_thumb_width = this.output_png_thumbnail_width
        browser_thumb_height = this.output_png_thumbnail_height
        convert_cmd = '%s -thumbnail %dx%d %s %s' % (this.convert_bin_fn, browser_thumb_width, browser_thumb_height, browser_png_local_fn, browser_thumb_local_fn)
        try:
            convert_result = subprocess.check_output(convert_cmd, shell = True)
        except subprocess.CalledProcessError as err:
            convert_result = "Error: Command '{}' returned with error (code {}): {}".format(err.cmd, err.returncode, err.output)
            sys.exit(-1)
        if debug:
            sys.stderr.write("Debug: Converted thumbnail file located at [%s]\n" % (browser_thumb_local_fn))

    # cf. http://stackoverflow.com/a/38346457/19410
    def predict_copytree_error(this, src, dst, debug=False):
        if os.path.exists(dst):
            src_isdir = os.path.isdir(src)
            dst_isdir = os.path.isdir(dst)
            if src_isdir and dst_isdir:
                pass
            elif src_isdir and not dst_isdir:
                yield {dst:'src is dir but dst is file.'}
            elif not src_isdir and dst_isdir:
                yield {dst:'src is file but dst is dir.'}
            else:
                yield {dst:'already exists a file with same name in dst'}

        if os.path.isdir(src):
            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(dst, item)
                for e in this.predict_copytree_error(s, d, debug):
                    yield e

    def copytree(this, src, dst, symlinks=False, ignore=None, overwrite=False, debug=False):
        if not overwrite:
            errors = list(this.predict_copytree_error(src, dst))
            if errors:
                raise Exception('Error: Copy would overwrite some files: [%s]\n' % errors)
        
        if not os.path.exists(dst):
            os.makedirs(dst)
            shutil.copystat(src, dst)
        lst = os.listdir(src)
        if ignore:
            excl = ignore(src, lst)
            lst = [x for x in lst if x not in excl]
        for item in lst:
            s = os.path.join(src, item)
            d = os.path.join(dst, item)
            if symlinks and os.path.islink(s):
                if os.path.lexists(d):
                    os.remove(d)
                os.symlink(os.readlink(s), d)
                try:
                    st = os.lstat(s)
                    mode = stat.S_IMODE(st.st_mode)
                    os.lchmod(d, mode)
                except:
                    pass  # lchmod not available
            elif os.path.isdir(s):
                this.copytree(s, d, symlinks, ignore)
            else:
                if not overwrite:
                    if os.path.exists(d):
                        continue
                shutil.copy2(s, d)

    def setup_gallery_skeleton_for_photoswipe(this, debug):
        # copy regions, pdfs and images folders to results dir
        this.output_regions_dir = os.path.join(this.output_dir, os.path.basename(this.temp_regions_results_dir))
        this.copytree(this.temp_regions_results_dir, this.output_regions_dir, debug)
        if debug:
            sys.stderr.write("Debug: Copied regions [%s] to [%s]\n" % (this.temp_regions_results_dir, this.output_regions_dir))
        this.output_pdf_dir = os.path.join(this.output_dir, os.path.basename(this.temp_pdf_results_dir))
        this.copytree(this.temp_pdf_results_dir, this.output_pdf_dir, debug)
        if debug:
            sys.stderr.write("Debug: Copied PDFs [%s] to [%s]\n" % (this.temp_pdf_results_dir, this.output_pdf_dir))
        this.output_png_dir = os.path.join(this.output_dir, os.path.basename(this.temp_png_results_dir))
        this.copytree(this.temp_png_results_dir, this.output_png_dir, debug)
        if debug:
            sys.stderr.write("Debug: Copied PNGs [%s] to [%s]\n" % (this.temp_png_results_dir, this.output_png_dir))        
        # copy gallery subdirs to results dir
        gallery_dist_dir = os.path.join(this.gallery_resources_dir, 'dist')
        output_dist_dir = os.path.join(this.output_dir, 'dist')
        this.copytree(gallery_dist_dir, output_dist_dir)
        if debug:
            sys.stderr.write("Debug: Copied gallery dist folder to output folder\n")

    def setup_gallery_skeleton_for_blueimp(this, debug):
        # copy regions, pdfs and images folders to results dir
        this.output_regions_dir = os.path.join(this.output_dir, os.path.basename(this.temp_regions_results_dir))
        this.copytree(this.temp_regions_results_dir, this.output_regions_dir, debug)
        if debug:
            sys.stderr.write("Debug: Copied regions [%s] to [%s]\n" % (this.temp_regions_results_dir, this.output_regions_dir))
        this.output_pdf_dir = os.path.join(this.output_dir, os.path.basename(this.temp_pdf_results_dir))
        this.copytree(this.temp_pdf_results_dir, this.output_pdf_dir, debug)
        if debug:
            sys.stderr.write("Debug: Copied PDFs [%s] to [%s]\n" % (this.temp_pdf_results_dir, this.output_pdf_dir))
        this.output_png_dir = os.path.join(this.output_dir, os.path.basename(this.temp_png_results_dir))
        this.copytree(this.temp_png_results_dir, this.output_png_dir, debug)
        if debug:
            sys.stderr.write("Debug: Copied PNGs [%s] to [%s]\n" % (this.temp_png_results_dir, this.output_png_dir))
        # copy gallery subdirs to results dir
        gallery_css_dir = os.path.join(this.gallery_resources_dir, 'css')
        gallery_img_dir = os.path.join(this.gallery_resources_dir, 'img')
        gallery_js_dir = os.path.join(this.gallery_resources_dir, 'js')
        output_css_dir = os.path.join(this.output_dir, 'css')
        output_img_dir = os.path.join(this.output_dir, 'img')
        output_js_dir = os.path.join(this.output_dir, 'js')
        this.copytree(gallery_css_dir, output_css_dir)
        this.copytree(gallery_img_dir, output_img_dir)
        this.copytree(gallery_js_dir, output_js_dir)
        if debug:
            sys.stderr.write("Debug: Copied gallery css, img and js folders to output folder\n")
        # copy octicons to results dir
        output_octicons_dir = os.path.join(this.output_dir, 'octicons')
        this.copytree(this.octicons_resources_dir, output_octicons_dir)
        if debug:
            sys.stderr.write("Debug: Copied Github Octicons resouces to output folder\n")

    def setup_gallery_parameters(this, title, debug):
        this.gallery_title = title
        this.gallery_timestamp = datetime.datetime.now().replace(microsecond=0).isoformat()

    def render_gallery_index_with_photoswipe_template(this, debug):
        this.setup_gallery_parameters(options.galleryTitle, debug)
        local_path = os.path.dirname(os.path.abspath(__file__))
        template_environment = jinja2.Environment(
            autoescape = False,
            loader = jinja2.FileSystemLoader(os.path.join(local_path, 'Gallery-templates-photoswipe')),
            trim_blocks = False
        )
        template_fn = 'index.html'
        gallery_index_fn = os.path.join(this.output_dir, 'index.html')
        image_urls = []
        image_widths = []
        image_heights = []
        thumbnail_urls = []
        pdf_urls = []
        external_urls = []
        titles = []
        descriptions = []
        genomic_regions = []
        for idx, region_id in enumerate(this.region_ids):
            image_url = 'images/' + region_id + '.png'
            identify_width_cmd = '%s -ping -format \'%%w\' %s/%s' % (this.identify_bin_fn, this.output_dir, image_url)
            image_width = None
            try:
                image_width = subprocess.check_output(identify_width_cmd, shell = True)
                if debug:
                    sys.stderr.write("Debug: Image URL width [%s]\n" % (image_width))
            except subprocess.CalledProcessError as err:
                identify_width_result = "Error: Command '{}' returned with error (code {}): {}".format(err.cmd, err.returncode, err.output)
                sys.stderr.write("%s\n" % (identify_width_result))
                sys.exit(-1)
            identify_height_cmd = '%s -ping -format \'%%h\' %s/%s' % (this.identify_bin_fn, this.output_dir, image_url)
            image_height = None
            try:
                image_height = subprocess.check_output(identify_height_cmd, shell = True)
                if debug:
                    sys.stderr.write("Debug: Image URL height [%s]\n" % (image_height))
            except subprocess.CalledProcessError as err:
                identify_height_result = "Error: Command '{}' returned with error (code {}): {}".format(err.cmd, err.returncode, err.output)
                sys.stderr.write("%s\n" % (identify_height_result))
                sys.exit(-1)
            image_urls.append(image_url)
            image_widths.append(int(image_width))
            image_heights.append(int(image_height))
            thumbnail_urls.append('images/thumbnails/' + region_id + '.png')
            pdf_urls.append('pdfs/' + region_id + '.pdf')
            region_obj = this.region_objs[idx]
            external_urls.append(this.browser_url + '/cgi-bin/hgTracks?db=' + this.browser_build_id + '&position=' + region_obj['chrom'] + '%3A' + region_obj['start'] + '-' + region_obj['stop'] + '&hgsid=' + this.browser_session_id)
            description_components = ['[' + this.browser_build_id + ']', region_obj['chrom'] + ":" + region_obj['start'] + '-' + region_obj['stop']]
            id_components = region_id.split("_")
            if len(id_components) > 5:
                description_components.append(id_components[5])
                titles.append(id_components[5])
            else:
                titles.append(region_id)
            description = ' '.join(description_components)
            descriptions.append(description)
            genomic_region = region_obj['chrom'] + ' : ' + region_obj['start'] + ' - ' + region_obj['stop']
            genomic_regions.append(genomic_region)
            
        render_context = {
            'title' : this.gallery_title,
            'timestamp' : this.gallery_timestamp,
            'image_data' : zip(image_urls, image_widths, image_heights, thumbnail_urls, pdf_urls, external_urls, titles, descriptions, genomic_regions)
        }
        with open(gallery_index_fn, "w") as gallery_index_fh:
            html = template_environment.get_template(template_fn).render(render_context).encode('utf-8')
            try:
                gallery_index_fh.write(html)
            except TypeError as te:
                gallery_index_fh.write(html.decode())
        if debug:
            sys.stderr.write("Debug: Wrote rendered gallery index file [%s]\n" % (gallery_index_fn))
        
    def render_gallery_index_with_blueimp_template(this, debug):
        this.setup_gallery_parameters(options.galleryTitle, debug)
        local_path = os.path.dirname(os.path.abspath(__file__))
        template_environment = jinja2.Environment(
            autoescape = False,
            loader = jinja2.FileSystemLoader(os.path.join(local_path, 'Gallery-templates-blueimp')),
            trim_blocks = False
        )
        template_fn = 'index.html'
        gallery_index_fn = os.path.join(this.output_dir, 'index.html')
        image_urls = []
        thumbnail_urls = []
        pdf_urls = []
        external_urls = []
        titles = []
        descriptions = []
        genomic_regions = []
        for idx, region_id in enumerate(this.region_ids):
            image_urls.append('images/' + region_id + '.png')
            thumbnail_urls.append('images/thumbnails/' + region_id + '.png')
            pdf_urls.append('pdfs/' + region_id + '.pdf')
            region_obj = this.region_objs[idx]
            external_urls.append(this.browser_url + '/cgi-bin/hgTracks?db=' + this.browser_build_id + '&position=' + region_obj['chrom'] + '%3A' + region_obj['start'] + '-' + region_obj['stop'] + '&hgsid=' + this.browser_session_id)
            description_components = ['[' + this.browser_build_id + ']', region_obj['chrom'] + ":" + region_obj['start'] + '-' + region_obj['stop']]
            id_components = region_id.split("_")
            if len(id_components) > 5:
                description_components.append(id_components[5])
                titles.append(id_components[5])
            else:
                titles.append(region_id)
            description = ' '.join(description_components)
            descriptions.append(description)
            genomic_region = region_obj['chrom'] + ' : ' + region_obj['start'] + ' - ' + region_obj['stop']
            genomic_regions.append(genomic_region)
            
        render_context = {
            'title' : this.gallery_title,
            'timestamp' : this.gallery_timestamp,
            'image_data' : zip(image_urls, thumbnail_urls, pdf_urls, external_urls, titles, descriptions, genomic_regions)
        }
        with open(gallery_index_fn, "w") as gallery_index_fh:
            html = template_environment.get_template(template_fn).render(render_context).encode('utf-8')
            try:
                gallery_index_fh.write(html)
            except TypeError as te:
                gallery_index_fh.write(html.decode())
        if debug:
            sys.stderr.write("Debug: Wrote rendered gallery index file [%s]\n" % (gallery_index_fn))

def main():
    if not options.regionsFn:
        sys.stderr.write("Error: Please specify a BED file of input regions\n\n")
        usage(-1)
    if not options.browserSessionID:
        sys.stderr.write("Error: Please specify a genome session ID\n\n")
        usage(-1)
    if not options.outputDir:
        sys.stderr.write("Error: Please specify an output directory\n\n")
        usage(-1)
    if not options.browserBuildID:
        sys.stderr.write("Error: Please specify an genome build ID (hg19, hg38, mm10, etc.)\n\n")
        usage(-1)
    if options.midpointAnnotation and options.intervalAnnotation:
        sys.stderr.write("Error: Please specify only one of midpoint or interval annotation flags\n\n")
        usage(-1)
    s.setup_midpoint_annotation(options.midpointAnnotation, options.verbose)
    s.setup_interval_annotation(options.intervalAnnotation, options.verbose)
    s.setup_annotation_rgba(options.annotationRgba, options.verbose)
    s.setup_annotation_font_point_size(options.annotationFontPointSize, options.verbose)
    s.setup_annotation_font_family(options.annotationFontFamily, options.verbose)
    s.setup_annotation_resolution(options.annotationResolution, options.verbose)
    s.setup_output_png_resolution(options.outputPngResolution, options.verbose)
    if options.rangePadding:
        s.setup_range_padding(options.rangePadding, options.verbose)
    s.setup_output_dir(options.outputDir, options.verbose)
    s.ensure_regions_fn(options.regionsFn, options.verbose)
    if not options.gallerySrcDir:
        if options.galleryMode == 'blueimp':
            options.gallerySrcDir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'Gallery-blueimp')
        elif options.galleryMode == 'photoswipe':
            options.gallerySrcDir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'Gallery-photoswipe')
        else:
            raise ValueError("Error: Please specify gallery mode from 'blueimp' or 'photoswipe' [{}]".format(options.galleryMode))
    s.ensure_gallery_src_dir(options.gallerySrcDir, options.verbose)
    if not options.octiconsSrcDir:
        options.octiconsSrcDir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'octicons')
    s.ensure_octicons_src_dir(options.octiconsSrcDir, options.verbose)
    if not options.convertBinFn:
        options.convertBinFn = s.find_convert_bin_fn_in_environment_path(options.verbose)
    s.ensure_convert_bin_fn(options.convertBinFn, options.verbose)
    if not options.identifyBinFn:
        options.identifyBinFn = s.find_identify_bin_fn_in_environment_path(options.verbose)
    s.ensure_identify_bin_fn(options.identifyBinFn, options.verbose)
    s.setup_temp_dirs(options.verbose)
    s.copy_regions_to_temp_regions_dir(options.verbose)
    s.annotate_temp_regions_with_custom_id(options.verbose)
    s.setup_browser_url(options.browserURL, options.verbose)
    s.setup_browser_username(options.browserUsername, options.verbose)
    s.setup_browser_password(options.browserPassword, options.verbose)
    s.setup_browser_authentication_type(options.useKerberosAuthentication, options.verbose)
    s.setup_browser_build_id(options.browserBuildID, options.verbose)
    s.setup_browser_session_id(options.browserSessionID, options.verbose)
    s.setup_browser_dump_url(options.verbose)
    s.setup_browser_pdf_url(options.verbose)
    s.generate_pdfs_from_annotated_regions(options.verbose)
    s.generate_pngs_from_pdfs(options.verbose)
    s.generate_thumbnails_from_pngs(options.verbose)
    if options.galleryMode == 'blueimp':
        s.setup_gallery_skeleton_for_blueimp(options.verbose)
        s.render_gallery_index_with_blueimp_template(options.verbose)
    elif options.galleryMode == 'photoswipe':
        s.setup_gallery_skeleton_for_photoswipe(options.verbose)
        s.render_gallery_index_with_photoswipe_template(options.verbose)
    else:
        raise ValueError("Error: Please specify gallery mode from 'blueimp' or 'photoswipe' [{}]".format(options.galleryMode))
    s.breakdown_temp_dir(options.verbose)

s = Soda()
if __name__ == "__main__":
    main()

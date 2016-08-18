#!/usr/bin/env python

"""soda.py

soda.py is a Python script that generates a gallery of images made from snapshots 
from a UCSC genome browser instance, so-called "soda plots". Snapshots are sourced 
from the main UCSC browser instance, but another instance can be used, if the host
name is specified.

You provide the script with four parameters:

* A BED-formatted file containing your regions of interest.
* The genome build name ('hg19', 'mm9', etc.)
* The session ID from your genome browser session, which specifies the browser 
  tracks you want to visualize, as well as other visual display parameters that 
  are specific to your session. 
* Where you want to store the gallery end-product.

"""

import sys
import os
import tempfile
import shutil
import requests
import optparse
import urllib
import json
import bs4
import re
import subprocess
import jinja2

default_title = "My Gallery"
default_genome_browser_url = "https://genome.ucsc.edu"
default_genome_browser_username = None
default_genome_browser_password = None
default_verbosity = False

parser = optparse.OptionParser()
parser.add_option("-r", "--regionsFn", action="store", type="string", dest="regionsFn", help="Path to BED-formatted regions of interest (required)")
parser.add_option("-s", "--browserSessionID", action="store", type="string", dest="browserSessionID", help="Genome browser session ID (required)")
parser.add_option("-o", "--outputDir", action="store", type="string", dest="outputDir", help="Output gallery directory (required)")
parser.add_option("-b", "--browserBuildID", action="store", type="string", dest="browserBuildID", help="Genome build ID (required)")
parser.add_option("-t", "--galleryTitle", action="store", type="string", dest="galleryTitle", default=default_title, help="Gallery title (optional)")
parser.add_option("-g", "--browserURL", action="store", type="string", dest="browserURL", default=default_genome_browser_url, help="Genome browser URL (optional)")
parser.add_option("-u", "--browserUsername", action="store", type="string", dest="browserUsername", default=default_genome_browser_username, help="Genome browser username (optional)")
parser.add_option("-p", "--browserPassword", action="store", type="string", dest="browserPassword", default=default_genome_browser_password, help="Genome browser password (optional)")
parser.add_option("-a", "--range", action="store", type="int", dest="rangePadding", help="Add or remove symmetrical padding to input regions (optional)")
parser.add_option("-l", "--gallerySrcDir", action="store", type="string", dest="gallerySrcDir", help="Blueimp Gallery resources directory (optional)")
parser.add_option("-c", "--octiconsSrcDir", action="store", type="string", dest="octiconsSrcDir", help="Github Octicons resources directory (optional)")
parser.add_option("-k", "--convertBinFn", action="store", type="string", dest="convertBinFn", help="ImageMagick convert binary path (optional)")
parser.add_option("-v", "--verbose", action="store_true", dest="verbose", default=default_verbosity, help="Print debug messages to stderr (optional)")
(options, args) = parser.parse_args()

def usage(errCode):
    args = ["-h"]
    (options, args) = parser.parse_args(args)
    sys.exit(errCode)

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
        self.browser_session_credentials = False
        self.browser_session_username = None
        self.browser_session_password = None
        self.browser_build_id = None
        self.region_ids = []
        self.region_objs = []
        self.range_padding = None
        self.convert_bin_fn = None
        self.output_png_resolution = 600
        self.output_png_thumbnail_width = 480
        self.output_png_thumbnail_height = 480

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
                annotation_id = None
                # skip if blank line
                if len(region_elements) == 1:
                    sys.stderr.write("Warning: Possible blank line in input regions file\n")
                    continue
                # adjust range, if set
                if this.range_padding:
                    try:
                        region_elements[1] = str(int(region_elements[1]) - this.range_padding)
                        region_elements[2] = str(int(region_elements[2]) + this.range_padding)
                        if region_elements[1] < 0:
                            region_elements[1] = 0
                    except IndexError as ie:
                        sys.stderr.write("Error: Region elements are [%d | %s]\n" % (len(region_elements), region_elements))
                        sys.exit(-1)
                # create modified ID from index, position and current ID, if available
                if len(region_elements) >= 4:
                    mod_id = region_elements[3]
                    mod_id = mod_id.replace(' ', '-')
                    mod_id = mod_id.replace(':', '-')
                    mod_id = mod_id.replace('_', '-')
                    annotation_id = "_".join(['plot', str(counter).zfill(zero_padding), region_elements[0], region_elements[1], region_elements[2], mod_id])
                elif len(region_elements) == 3:
                    annotation_id = "_".join(['plot', str(counter).zfill(zero_padding), region_elements[0], region_elements[1], region_elements[2]])
                if annotation_id:
                    annotated_line = '\t'.join([region_elements[0], region_elements[1], region_elements[2], annotation_id]) + '\n'
                    this.temp_annotated_regions_fh.write(annotated_line)
                counter = counter + 1
        if debug:
            sys.stderr.write("Debug: Annotated regions file written to [%s]\n" % (this.temp_annotated_regions_fn))  
        this.temp_annotated_regions_fh.close()

    def setup_browser_url(this, browserURL, debug):
        this.browser_url = browserURL
        if browserURL != default_genome_browser_url:
            options.browserUsername = None
            options.browserPassword = None
            sys.stderr.write("Warning: Browser URL was changed from default; credentials were blanked out\n")
        if debug:
            sys.stderr.write("Debug: Browser URL set to [%s]\n" % (this.browser_url))
        
    def setup_browser_username(this, browserUsername, debug):
        this.browser_username = browserUsername
        this.browser_session_credentials = True
        if debug:
            sys.stderr.write("Debug: Browser username set to [%s]\n" % (this.browser_username))

    def setup_browser_password(this, browserPassword, debug):
        this.browser_password = browserPassword
        this.browser_session_credentials = True
        if debug:
            sys.stderr.write("Debug: Browser password set to [%s]\n" % (this.browser_password))

    def setup_browser_build_id(this, browserBuildID, debug):
        this.browser_build_id = browserBuildID
        if debug:
            sys.stderr.write("Debug: Browser build ID set to [%s]\n" % (this.browser_build_id))

    def setup_browser_dump_url(this, debug):
        this.browser_dump_url = this.browser_url + '/cgi-bin/cartDump'
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
                    u"chrom" : region_elements[0],
                    u"start" : region_elements[1],
                    u"stop"  : region_elements[2],
                    u"id"    : region_elements[3]
                }
                region_id = region_obj['id']
                this.region_objs.append(region_obj)
                this.region_ids.append(region_id)
                this.generate_pdf_from_annotated_region(region_obj, region_id, debug)

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
        if this.browser_session_credentials:
            browser_credentials = requests.auth.HTTPBasicAuth(this.browser_username, this.browser_password)
        browser_cartdump_response = requests.post(
            url = this.browser_dump_url,
            data = browser_post_body,
            auth = browser_credentials,
            verify = False,
        )
        # write response text to cartDump in temporary output folder
        browser_cartdump_response_content = browser_cartdump_response.content
        cart_dump_fn = os.path.join(this.temp_pdf_results_dir, 'cartDump')
        if debug:
            sys.stderr.write("Debug: Writing cart dump response content to [%s]\n" % (cart_dump_fn))
        cart_dump_fh = open(cart_dump_fn, "w")
        cart_dump_fh.write(browser_cartdump_response_content)
        cart_dump_fh.close()
        # ensure cartDump exists
        if not os.path.exists(cart_dump_fn):
            sys.stderr.write("Error: Could not write cart dump data to [%s]\n" % (cart_dump_fn))
            sys.exit(-1)
        # get PDF URL
        browser_pdf_url_response = requests.get(
            url = this.browser_pdf_url,
            auth = browser_credentials,
            verify = False
        )
        browser_pdf_url_soup = bs4.BeautifulSoup(browser_pdf_url_response.text, "html.parser")
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
        # fetch PDF
        if len(browser_pdf_url_soup_hrefs_converted) != 1:
            sys.stderr.write("Error: No or more than one PDF available for this region\n")
            usage(-1)
        browser_pdf_url = browser_pdf_url_soup_hrefs_converted[0]
        browser_pdf_response = requests.get(
            url = browser_pdf_url,
            stream = True,
            auth = browser_credentials,
            verify = False,
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

    def generate_pngs_from_pdfs(this, debug):
        for region_id in this.region_ids:
            this.generate_png_from_pdf(region_id, debug)

    def generate_png_from_pdf(this, region_id, debug):
        browser_pdf_local_fn = os.path.join(this.temp_pdf_results_dir, region_id + '.pdf')
        browser_png_local_fn = os.path.join(this.temp_png_results_dir, region_id + '.png')
        convert_cmd = '%s -density %d %s -background white -flatten %s' % (this.convert_bin_fn, this.output_png_resolution, browser_pdf_local_fn, browser_png_local_fn)
        try:
            convert_result = subprocess.check_output(convert_cmd, shell = True)
        except subprocess.CalledProcessError as err:
            convert_result = "Error: Command '{}' returned with error (code {}): {}".format(err.cmd, err.returncode, err.output)
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

    def setup_gallery_skeleton(this, debug):
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
        
    def render_gallery_index(this, debug):
        this.setup_gallery_parameters(options.galleryTitle, debug)
        local_path = os.path.dirname(os.path.abspath(__file__))
        template_environment = jinja2.Environment(
            autoescape = False,
            loader = jinja2.FileSystemLoader(os.path.join(local_path, 'Gallery-templates')),
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
            
        render_context = {
            'title' : this.gallery_title,
            'image_data' : zip(image_urls, thumbnail_urls, pdf_urls, external_urls, titles, descriptions)
        }
        with open(gallery_index_fn, "w") as gallery_index_fh:
            html = template_environment.get_template(template_fn).render(render_context).encode('utf-8')
            gallery_index_fh.write(html)
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
    if options.rangePadding:
        s.setup_range_padding(options.rangePadding, options.verbose)
    s.setup_output_dir(options.outputDir, options.verbose)
    s.ensure_regions_fn(options.regionsFn, options.verbose)
    if not options.gallerySrcDir:
        options.gallerySrcDir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'Gallery')
    s.ensure_gallery_src_dir(options.gallerySrcDir, options.verbose)
    if not options.octiconsSrcDir:
        options.octiconsSrcDir = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'octicons')
    s.ensure_octicons_src_dir(options.octiconsSrcDir, options.verbose)
    if not options.convertBinFn:
        options.convertBinFn = s.find_convert_bin_fn_in_environment_path(options.verbose)
    s.ensure_convert_bin_fn(options.convertBinFn, options.verbose)
    s.setup_temp_dirs(options.verbose)
    s.copy_regions_to_temp_regions_dir(options.verbose)
    s.annotate_temp_regions_with_custom_id(options.verbose)
    s.setup_browser_url(options.browserURL, options.verbose)
    s.setup_browser_username(options.browserUsername, options.verbose)
    s.setup_browser_password(options.browserPassword, options.verbose)
    s.setup_browser_build_id(options.browserBuildID, options.verbose)
    s.setup_browser_session_id(options.browserSessionID, options.verbose)
    s.setup_browser_dump_url(options.verbose)
    s.setup_browser_pdf_url(options.verbose)
    s.generate_pdfs_from_annotated_regions(options.verbose)
    s.generate_pngs_from_pdfs(options.verbose)
    s.generate_thumbnails_from_pngs(options.verbose)
    s.setup_gallery_skeleton(options.verbose)
    s.render_gallery_index(options.verbose)
    s.breakdown_temp_dir(options.verbose)

s = Soda()
if __name__ == "__main__":
    main()

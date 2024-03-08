# soda
Python-based UCSC genome browser snapshot gallery-maker

- [Description](#description)
- [Dependencies](#dependencies)
- [Usage](#usage)
- [Options](#options)
- [Credits](#credits)

## Description

`soda` is a Python script that generates a gallery of images made from snapshots from a UCSC genome browser instance, so-called "soda plots". Snapshots can be derived from an external browser instance, by pointing `soda` to that browser instance's host name.

You provide the script with four required parameters:

1. A BED-formatted file containing your regions of interest.
2. The genome build name, such as `hg19`, `hg38`, `mm10`, etc.
3. The [session ID](https://genome.ucsc.edu/goldenpath/help/hgSessionHelp.html) from your genome browser session, which specifies the browser tracks you want to visualize, as well as other visual display parameters that are specific to your session.
4. Where you want to store the gallery end-product.

If the BED file contains a fourth column (commonly used to store the [name](https://genome.ucsc.edu/FAQ/FAQformat.html#format1) of the region), its values are used as labels for each page in the gallery.

Additional options are available; please see the [Options](#options) section.

### Note

The BED file does not need to be in BEDOPS `sort-bed` order. In fact, it can be useful to order the regions in a BED file by some criteria other than genomic position, such as some numerical value stored in the BED file's score column, *e.g.*:

```bash
$ sort -k5,5n input.bed > input_sorted_by_scores.bed
```

Any ordering is allowed. Gallery snapshots are presented in the same order as rows in the input BED file.

## Installation

Set up a virtual environment via `virtualenv` or `conda create` and activate it. Then install via `pip`:

```bash
$ python3 -m pip install soda-gallery
```

Or via [Bioconda](https://bioconda.github.io/index.html):

```bash
$ conda config --add channels bioconda
$ conda install soda-gallery
```

### Development

Clone it from Github and install locally into a virtual environment:

```bash
$ git clone https://github.com/alexpreynolds/soda.git
$ cd soda
$ python3 -m pip install -e .
```

## Usage

As a usage example, you may have a BED file in some home directory called `/home/abc/regions.bed`. You have a session ID from the UCSC genome browser called `123456_abcdef`, with all your tracks selected and display parameters set, using `hg38` as the reference genome build. Finally, you want to store the results in a folder called `/home/abc/my-soda-plot-results`:

```bash
$ soda -r "/home/abc/regions.bed" -b "hg38" -s "123456_abcdef" -o "/home/abc/my-soda-plot-results"
```

If you run this locally, you can open the result folder's `index.html` file with your web browser to load the gallery. For example, from the Terminal application in OS X, you can run:

```bash
$ open /Users/abc/my-soda-plot-results/index.html
```

which opens the gallery index in your default web browser.

## Options

A full listing of options is available via `soda --help`.

### Required

Four options are required. At minimum:

```bash
-r, --regionsFn
```

Use `-r` or `--regionsFn` to specify the path to the input BED file containing regions of interest.

```bash
-b, --browserBuildID
```

The `-b` or `--browserBuildID` option specifies the genome build, *e.g.*, `hg19`, `mm10`, etc.

```bash
-s, --browserSessionID
```

The `-s` or `--browserSessionID` option specify the browser session ID, which references a configuration of tracks and display parameters from a genome browser instance.

```bash
-o, --outputDir
```

Use the `-o` or `--outputDir` option to specify where the image gallery is saved. If this path already exists, `soda` will exit with a fatal error message.

### Optional

Other options are available depending on how you want to customize the run.

```bash
-t, --title
```

Use `-t` or `--title` to specify a gallery title.

```bash
[ -i, --addIntervalAnnotation | -d, --addMidpointAnnotation ]
```

Use `-i` or `--addIntervalAnnotation` to add a rectangle underneath all tracks that demarcates the original genomic range (useful when used with `--range`). Alternatively, use `-d` or `--addMidpointAnnotation` to add a vertical line underneath all tracks, centered on the midpoint of the input genomic range. In both cases, the annotation is labeled with the genomic coordinates of the original interval or the calculated midpoint, respectively. It is not allowed to specify both options together.

```bash
-w, --annotationRgba
-z, --annotationFontPointSize
-f, --annotationFontFamily
```

When used with `-i` or `-d` to add an interval or midpoint annotation, these options may be used to override the default [`rgba()` color](http://www.w3schools.com/cssref/css_colors_legal.asp), typeface point size, and typeface family (where supported by the local installation of ImageMagick), which are parameters used to render the appearance of the annotation components. The default color is `rgba(255, 0, 0, 0.333)` and the default point size and font family values are `5` and `Helvetica-Bold`, respectively. 

```bash
-a, --range
```

Use the `-a` or `--range` option to pad the BED input's **midpoint** symmetrically by the specified number of bases. This works regardless of the sort order of the input.

```bash
-g, --browserURL
```

Use the `-g` or `--browserURL` option to specify a different genome browser URL other than the UCSC genome browser. If a different host is specified and credentials are required, please use the `-u` and `-p` options (see below).

```bash
-u, --browserUsername
-p, --browserPassword
```

Use these two options to specify a username and password for the browser instance, if you pick a different `--browserURL` and that browser instance requires basic credentials. If these options are not specified, no credentials are passed along. If authentication is required and it fails, `soda` may exit with an error.

```bash
-y, --useKerberosAuthentication
```

Use this option if access to your custom browser instance requires a Kerberos ticket (obtained via ``kinit``, for example).

```bash
-v, --verbose
```

Use `-v` or `--verbose` to print debug messages, which may be useful for automation or debugging.

Use the `-m` option to specify the gallery framework. The default is `photoswipe`; alternatively, use `blueimp` to generate a blueimp-backed gallery.

## Credits

The general "soda" gallery tool has been authored in various `bash`- and Perl-flavored incarnations since 2008 by primary authors Richard Sandstrom and Scott Kuehn, with modifications over time by Bob Thurman, Jay Hesselberth, Richard Humbert, Brady Miller and Alex Reynolds.

This Python rewrite and new functionality were authored by Alex Reynolds.

This tool uses the [PhotoSwipe](https://github.com/dimsemenov/photoswipe), [blueimp Gallery](https://github.com/blueimp/Gallery) and [Github octicons](https://github.com/primer/octicons) projects, which are MIT-licensed.

## So what's up with the name?

"Scott Kuehn: he came up with the name. The legend is that when asked what to call the program, he lifted a can of cola, sighed deeply, and said: 'soda plot'." - R. Sandstrom

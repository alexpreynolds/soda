# soda.py
Python-based UCSC genome browser snapshot gallery-maker

- [Description](#description)
- [Dependencies](#dependencies)
- [Usage](#usage)
- [Options](#options)

## Description

`soda.py` is a Python script that generates a gallery of images made from snapshots from a UCSC genome browser instance, so-called "soda plots". Snapshots can be derived from an external browser instance, by pointing `soda.py` to that browser instance's host name.

You provide the script with four required parameters:

1. A BED-formatted file containing your regions of interest.
2. The genome build name, such as `hg19`, `hg38`, `mm10`, etc.
3. The [session ID](https://genome.ucsc.edu/goldenpath/help/hgSessionHelp.html) from your genome browser session, which specifies the browser tracks you want to visualize, as well as other visual display parameters that are specific to your session.
4. Where you want to store the gallery end-product.

If the BED file contains a fourth column (commonly used to store the [name](https://genome.ucsc.edu/FAQ/FAQformat.html#format1) of the region), its values are used as labels for each page in the gallery.

Additional options are available; please see the [Options](#options) section.

### Note

Gallery snapshots are presented in the same order as rows in the input BED file. The BED file does not need to be in [BEDOPS `sort-bed`](http://bedops.readthedocs.io/en/latest/content/reference/file-management/sorting/sort-bed.html) order. In fact, it can be useful to order the regions in a BED file by some criteria other than genomic position, such as some numerical value stored in the BED file's score column, *e.g.*:

```bash
$ sort -k5,5n input.bed > input_sorted_by_scores.bed
```

Any ordering is allowed.

## Download

To grab this kit, you can clone it from Github:

```bash
$ git clone https://github.com/alexpreynolds/soda.git
```

## Dependencies

`soda.py` relies on Python 2.7 and up with [Beautiful Soup](https://pypi.python.org/pypi/beautifulsoup4) and [Jinja2](https://pypi.python.org/pypi/Jinja2), as well as binaries in [ImageMagick](http://www.imagemagick.org). Installing these dependencies may require administrator privileges. Please see the documentation for these components for installation instructions, or contact IT support for assistance.

## Usage

As a usage example, you may have a BED file in some home directory called `/home/abc/regions.bed`. You have a session ID from the UCSC genome browser called `123456_abcdef`, with all your tracks selected and display parameters set, using `hg38` as the reference genome build. Finally, you want to store the results in a folder called `/home/abc/my-soda-plot-results`:

```bash
$ /path/to/soda.py -r "/home/abc/regions.bed" -b "hg38" -s "123456_abcdef" -o "/home/abc/my-soda-plot-results"
```

If you run this locally, you can open the result folder's `index.html` file with your web browser to load the gallery. For example, from the Terminal application in OS X, you can run:

```bash
$ open /Users/abc/my-soda-plot-results/index.html
```

which opens the gallery index in your default web browser.

## Options

Other options are available depending on how you want to customize the run.

```bash
-t, --title
```

Use `-t` or `--title` to specify a gallery title.

```bash
-a, --range
```

Use the `-a` or `--range` option to pad the BED input symmetrically by the specified number of bases. This is similar to applying operations with BEDOPS `bedops --range`, except that this works regardless of the sort order of the input.

```bash
-g, --browserURL
```

Use the `-g` or `--browserURL` option to specify a different genome browser URL other than the USCS genome browser. If a different host is specified and credentials are required, please use the `-u` and `-p` options (see below).

```bash
-u, --browserUsername
-p, --browserPassword
```

Use these two options to specify a username and password for the browser instance, if you pick a different `--browserURL` and that browser instance requires basic credentials. If these options are not specified, no credentials are passed along. If authentication is required and it fails, `soda.py` may exit with an error.

```bash
-v, --verbose
```

Use `-v` or `--verbose` to print debug messages, which may be useful for automation or debugging.
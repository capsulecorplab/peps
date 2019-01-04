#!/usr/bin/env python
"""Convert SEPs to (X)HTML - courtesy of /F

Usage: %(PROGRAM)s [options] [<seps> ...]

Options:

-u, --user
    python.org username

-b, --browse
    After generating the HTML, direct your web browser to view it
    (using the Python webbrowser module).  If both -i and -b are
    given, this will browse the on-line HTML; otherwise it will
    browse the local HTML.  If no sep arguments are given, this
    will browse SEP 0.

-i, --install
    After generating the HTML, install it and the plaintext source file
    (.txt) on python.org.  In that case the user's name is used in the scp
    and ssh commands, unless "-u username" is given (in which case, it is
    used instead).  Without -i, -u is ignored.

-l, --local
    Same as -i/--install, except install on the local machine.  Use this
    when logged in to the python.org machine (dinsdale).

-q, --quiet
    Turn off verbose messages.

-h, --help
    Print this help message and exit.

The optional arguments ``seps`` are either sep numbers, .rst or .txt files.
"""

from __future__ import print_function, unicode_literals

import sys
import os
import re
import glob
import getopt
import errno
import random
import time
from io import open

try:
    from html import escape
except ImportError:
    from cgi import escape

from docutils import core, nodes, utils
from docutils.readers import standalone
from docutils.transforms import peps, references, misc, frontmatter, Transform
from docutils.parsers import rst


class DataError(Exception):
    pass


REQUIRES = {"python": "2.6", "docutils": "0.2.7"}
PROGRAM = sys.argv[0]
RFCURL = "http://www.faqs.org/rfcs/rfc%d.html"
SEPURL = "sep-%04d.html"
SEPCVSURL = "https://hg.python.org/peps/file/tip/pep-%04d.txt"
SEPDIRRUL = "http://www.python.org/peps/"


HOST = "dinsdale.python.org"  # host for update
HDIR = "/data/ftp.python.org/pub/www.python.org/seps"  # target host directory
LOCALVARS = "Local Variables:"

COMMENT = """<!--
This HTML is auto-generated.  DO NOT EDIT THIS FILE!  If you are writing a new
SEP, see http://www.python.org/seps/sep-0001.html for instructions and links
to templates.  DO NOT USE THIS HTML FILE AS YOUR TEMPLATE!
-->"""

# The generated HTML doesn't validate -- you cannot use <hr> and <h3> inside
# <pre> tags.  But if I change that, the result doesn't look very nice...
DTD = (
    '<!DOCTYPE html PUBLIC "-//W3C//DTD HTML 4.0 Transitional//EN"\n'
    '                      "http://www.w3.org/TR/REC-html40/loose.dtd">'
)

fixpat = re.compile(
    "((https?|ftp):[-_a-zA-Z0-9/.+~:?#$=&,]+)|(sep-\d+(.txt|.rst)?)|"
    "(RFC[- ]?(?P<rfcnum>\d+))|"
    "(SEP\s+(?P<sepnum>\d+))|"
    "."
)

EMPTYSTRING = ""
SPACE = " "
COMMASPACE = ", "


def usage(code, msg=""):
    """Print usage message and exit.  Uses stderr if code != 0."""
    if code == 0:
        out = sys.stdout
    else:
        out = sys.stderr
    print(__doc__ % globals(), file=out)
    if msg:
        print(msg, file=out)
    sys.exit(code)


def fixanchor(current, match):
    text = match.group(0)
    link = None
    if text.startswith("http:") or text.startswith("https:") or text.startswith("ftp:"):
        # Strip off trailing punctuation.  Pattern taken from faqwiz.
        ltext = list(text)
        while ltext:
            c = ltext.pop()
            if c not in "();:,.?'\"<>":
                ltext.append(c)
                break
        link = EMPTYSTRING.join(ltext)
    elif text.startswith("sep-") and text != current:
        link = os.path.splitext(text)[0] + ".html"
    elif text.startswith("SEP"):
        sepnum = int(match.group("sepnum"))
        link = SEPURL % sepnum
    elif text.startswith("RFC"):
        rfcnum = int(match.group("rfcnum"))
        link = RFCURL % rfcnum
    if link:
        return '<a href="%s">%s</a>' % (escape(link), escape(text))
    return escape(match.group(0))  # really slow, but it works...


NON_MASKED_EMAILS = [
    "seps@python.org",
    "python-list@python.org",
    "python-dev@python.org",
]


def fixemail(address, sepno):
    if address.lower() in NON_MASKED_EMAILS:
        # return hyperlinked version of email address
        return linkemail(address, sepno)
    else:
        # return masked version of email address
        parts = address.split("@", 1)
        return "%s&#32;&#97;t&#32;%s" % (parts[0], parts[1])


def linkemail(address, sepno):
    parts = address.split("@", 1)
    return (
        '<a href="mailto:%s&#64;%s?subject=SEP%%20%s">'
        "%s&#32;&#97;t&#32;%s</a>" % (parts[0], parts[1], sepno, parts[0], parts[1])
    )


def fixfile(inpath, input_lines, outfile):
    try:
        from email.Utils import parseaddr
    except ImportError:
        from email.utils import parseaddr
    basename = os.path.basename(inpath)
    infile = iter(input_lines)
    # convert plaintext sep to minimal XHTML markup
    print(DTD, file=outfile)
    print("<html>", file=outfile)
    print(COMMENT, file=outfile)
    print("<head>", file=outfile)
    # head
    header = []
    sep = ""
    title = ""
    for line in infile:
        if not line.strip():
            break
        if line[0].strip():
            if ":" not in line:
                break
            key, value = line.split(":", 1)
            value = value.strip()
            header.append((key, value))
        else:
            # continuation line
            key, value = header[-1]
            value = value + line
            header[-1] = key, value
        if key.lower() == "title":
            title = value
        elif key.lower() == "sep":
            sep = value
    if sep:
        title = "SEP " + sep + " -- " + title
    if title:
        print("  <title>%s</title>" % escape(title), file=outfile)
    r = random.choice(list(range(64)))
    print(
        (
            '  <link rel="STYLESHEET" href="style.css" type="text/css" />\n'
            "</head>\n"
            '<body bgcolor="white">\n'
            '<table class="navigation" cellpadding="0" cellspacing="0"\n'
            '       width="100%%" border="0">\n'
            '<tr><td class="navicon" width="150" height="35">\n'
            '<a href="../" title="Python Home Page">\n'
            '<img src="../pics/PyBanner%03d.gif" alt="[Python]"\n'
            ' border="0" width="150" height="35" /></a></td>\n'
            '<td class="textlinks" align="left">\n'
            '[<b><a href="../">Python Home</a></b>]' % r
        ),
        file=outfile,
    )
    if basename != "sep-0000.txt":
        print('[<b><a href=".">SEP Index</a></b>]', file=outfile)
    if sep:
        try:
            print(
                ('[<b><a href="sep-%04d.txt">SEP Source</a>' "</b>]" % int(sep)),
                file=outfile,
            )
        except ValueError as error:
            print(("ValueError (invalid SEP number): %s" % error), file=sys.stderr)
    print("</td></tr></table>", file=outfile)
    print('<div class="header">\n<table border="0">', file=outfile)
    for k, v in header:
        if k.lower() in ("author", "bdfl-delegate", "discussions-to"):
            mailtos = []
            for part in re.split(",\s*", v):
                if "@" in part:
                    realname, addr = parseaddr(part)
                    if k.lower() == "discussions-to":
                        m = linkemail(addr, sep)
                    else:
                        m = fixemail(addr, sep)
                    mailtos.append("%s &lt;%s&gt;" % (realname, m))
                elif part.startswith("http:"):
                    mailtos.append('<a href="%s">%s</a>' % (part, part))
                else:
                    mailtos.append(part)
            v = COMMASPACE.join(mailtos)
        elif k.lower() in ("replaces", "superseded-by", "requires"):
            otherseps = ""
            for othersep in re.split(",?\s+", v):
                othersep = int(othersep)
                otherseps += '<a href="sep-%04d.html">%i</a> ' % (othersep, othersep)
            v = otherseps
        elif k.lower() in ("last-modified",):
            date = v or time.strftime("%d-%b-%Y", time.localtime(os.stat(inpath)[8]))
            if date.startswith("$" "Date: ") and date.endswith(" $"):
                date = date[6:-2]
            if basename == "sep-0000.txt":
                v = date
            else:
                try:
                    url = SEPCVSURL % int(sep)
                    v = '<a href="%s">%s</a> ' % (url, escape(date))
                except ValueError as error:
                    v = date
        elif k.lower() in ("content-type",):
            url = SEPURL % 9
            sep_type = v or "text/plain"
            v = '<a href="%s">%s</a> ' % (url, escape(sep_type))
        elif k.lower() == "version":
            if v.startswith("$" "Revision: ") and v.endswith(" $"):
                v = escape(v[11:-2])
        else:
            v = escape(v)
        print("  <tr><th>%s:&nbsp;</th><td>%s</td></tr>" % (escape(k), v), file=outfile)
    print("</table>", file=outfile)
    print("</div>", file=outfile)
    print("<hr />", file=outfile)
    print('<div class="content">', file=outfile)
    need_pre = 1
    for line in infile:
        if line[0] == "\f":
            continue
        if line.strip() == LOCALVARS:
            break
        if line[0].strip():
            if not need_pre:
                print("</pre>", file=outfile)
            print("<h3>%s</h3>" % line.strip(), file=outfile)
            need_pre = 1
        elif not line.strip() and need_pre:
            continue
        else:
            # SEP 0 has some special treatment
            if basename == "sep-0000.txt":
                parts = line.split()
                if len(parts) > 1 and re.match(r"\s*\d{1,4}", parts[1]):
                    # This is a SEP summary line, which we need to hyperlink
                    url = SEPURL % int(parts[1])
                    if need_pre:
                        print("<pre>", file=outfile)
                        need_pre = 0
                    print(
                        re.sub(
                            parts[1], '<a href="%s">%s</a>' % (url, parts[1]), line, 1
                        ),
                        end="",
                        file=outfile,
                    )
                    continue
                elif parts and "@" in parts[-1]:
                    # This is a sep email address line, so filter it.
                    url = fixemail(parts[-1], sep)
                    if need_pre:
                        print("<pre>", file=outfile)
                        need_pre = 0
                    print(re.sub(parts[-1], url, line, 1), end="", file=outfile)
                    continue
            line = fixpat.sub(lambda x, c=inpath: fixanchor(c, x), line)
            if need_pre:
                print("<pre>", file=outfile)
                need_pre = 0
            outfile.write(line)
    if not need_pre:
        print("</pre>", file=outfile)
    print("</div>", file=outfile)
    print("</body>", file=outfile)
    print("</html>", file=outfile)


docutils_settings = None
"""Runtime settings object used by Docutils.  Can be set by the client
application when this module is imported."""


class SEPHeaders(Transform):

    """
    Process fields in a SEP's initial RFC-2822 header.
    """

    default_priority = 360

    sep_url = "sep-%04d"
    sep_cvs_url = SEPCVSURL
    rcs_keyword_substitutions = (
        (re.compile(r"\$" r"RCSfile: (.+),v \$$", re.IGNORECASE), r"\1"),
        (re.compile(r"\$[a-zA-Z]+: (.+) \$$"), r"\1"),
    )

    def apply(self):
        if not len(self.document):
            # @@@ replace these DataErrors with proper system messages
            raise DataError("Document tree is empty.")
        header = self.document[0]
        if (
            not isinstance(header, nodes.field_list)
            or "rfc2822" not in header["classes"]
        ):
            raise DataError(
                "Document does not begin with an RFC-2822 " "header; it is not a SEP."
            )
        sep = None
        for field in header:
            if field[0].astext().lower() == "sep":  # should be the first field
                value = field[1].astext()
                try:
                    sep = int(value)
                    cvs_url = self.sep_cvs_url % sep
                except ValueError:
                    sep = value
                    cvs_url = None
                    msg = self.document.reporter.warning(
                        '"SEP" header must contain an integer; "%s" is an '
                        "invalid value." % sep,
                        base_node=field,
                    )
                    msgid = self.document.set_id(msg)
                    prb = nodes.problematic(value, value or "(none)", refid=msgid)
                    prbid = self.document.set_id(prb)
                    msg.add_backref(prbid)
                    if len(field[1]):
                        field[1][0][:] = [prb]
                    else:
                        field[1] += nodes.paragraph("", "", prb)
                break
        if sep is None:
            raise DataError('Document does not contain an RFC-2822 "SEP" ' "header.")
        if sep == 0:
            # Special processing for SEP 0.
            pending = nodes.pending(peps.PEPZero)
            self.document.insert(1, pending)
            self.document.note_pending(pending)
        if len(header) < 2 or header[1][0].astext().lower() != "title":
            raise DataError("No title!")
        for field in header:
            name = field[0].astext().lower()
            body = field[1]
            if len(body) > 1:
                raise DataError(
                    "SEP header field body contains multiple "
                    "elements:\n%s" % field.pformat(level=1)
                )
            elif len(body) == 1:
                if not isinstance(body[0], nodes.paragraph):
                    raise DataError(
                        "SEP header field body may only contain "
                        "a single paragraph:\n%s" % field.pformat(level=1)
                    )
            elif name == "last-modified":
                date = time.strftime(
                    "%d-%b-%Y", time.localtime(os.stat(self.document["source"])[8])
                )
                if cvs_url:
                    body += nodes.paragraph(
                        "", "", nodes.reference("", date, refuri=cvs_url)
                    )
            else:
                # empty
                continue
            para = body[0]
            if name in ("author", "bdfl-delegate"):
                for node in para:
                    if isinstance(node, nodes.reference):
                        node.replace_self(peps.mask_email(node))
            elif name == "discussions-to":
                for node in para:
                    if isinstance(node, nodes.reference):
                        node.replace_self(peps.mask_email(node, sep))
            elif name in ("replaces", "superseded-by", "requires"):
                newbody = []
                space = nodes.Text(" ")
                for refsep in re.split(r",?\s+", body.astext()):
                    sepno = int(refsep)
                    newbody.append(
                        nodes.reference(
                            refsep,
                            refsep,
                            refuri=(
                                self.document.settings.sep_base_url
                                + self.sep_url % sepno
                            ),
                        )
                    )
                    newbody.append(space)
                para[:] = newbody[:-1]  # drop trailing space
            elif name == "last-modified":
                utils.clean_rcs_keywords(para, self.rcs_keyword_substitutions)
                if cvs_url:
                    date = para.astext()
                    para[:] = [nodes.reference("", date, refuri=cvs_url)]
            elif name == "content-type":
                sep_type = para.astext()
                uri = self.document.settings.sep_base_url + self.sep_url % 12
                para[:] = [nodes.reference("", sep_type, refuri=uri)]
            elif name == "version" and len(body):
                utils.clean_rcs_keywords(para, self.rcs_keyword_substitutions)


class SEPReader(standalone.Reader):

    supported = ("sep",)
    """Contexts this reader supports."""

    settings_spec = (
        "SEP Reader Option Defaults",
        "The --sep-references and --rfc-references options (for the "
        "reStructuredText parser) are on by default.",
        (),
    )

    config_section = "sep reader"
    config_section_dependencies = ("readers", "standalone reader")

    def get_transforms(self):
        transforms = standalone.Reader.get_transforms(self)
        # We have SEP-specific frontmatter handling.
        transforms.remove(frontmatter.DocTitle)
        transforms.remove(frontmatter.SectionSubTitle)
        transforms.remove(frontmatter.DocInfo)
        transforms.extend([SEPHeaders, peps.Contents, peps.TargetNotes])
        return transforms

    settings_default_overrides = {"sep_references": 1, "rfc_references": 1}

    inliner_class = rst.states.Inliner

    def __init__(self, parser=None, parser_name=None):
        """`parser` should be ``None``."""
        if parser is None:
            parser = rst.Parser(rfc2822=True, inliner=self.inliner_class())
        standalone.Reader.__init__(self, parser, "")


def fix_rst_sep(inpath, input_lines, outfile):
    output = core.publish_string(
        source="".join(input_lines),
        source_path=inpath,
        destination_path=outfile.name,
        reader=SEPReader(),
        parser_name="restructuredtext",
        writer_name="pep_html",
        settings=docutils_settings,
        # Allow Docutils traceback if there's an exception:
        settings_overrides={"traceback": 1, "halt_level": 2},
    )
    outfile.write(output.decode("utf-8"))


def get_sep_type(input_lines):
    """
    Return the Content-Type of the input.  "text/plain" is the default.
    Return ``None`` if the input is not a SEP.
    """
    sep_type = None
    for line in input_lines:
        line = line.rstrip().lower()
        if not line:
            # End of the RFC 2822 header (first blank line).
            break
        elif line.startswith("content-type: "):
            sep_type = line.split()[1] or "text/plain"
            break
        elif line.startswith("sep: "):
            # Default SEP type, used if no explicit content-type specified:
            sep_type = "text/plain"
    return sep_type


def get_input_lines(inpath):
    try:
        infile = open(inpath, encoding="utf-8")
    except IOError as e:
        if e.errno != errno.ENOENT:
            raise
        print("Error: Skipping missing SEP file:", e.filename, file=sys.stderr)
        sys.stderr.flush()
        return None
    lines = infile.read().splitlines(1)  # handles x-platform line endings
    infile.close()
    return lines


def find_sep(sep_str):
    """Find the .rst or .txt file indicated by a cmd line argument"""
    if os.path.exists(sep_str):
        return sep_str
    num = int(sep_str)
    rstpath = "sep-%04d.rst" % num
    if os.path.exists(rstpath):
        return rstpath
    return "sep-%04d.txt" % num


def make_html(inpath, verbose=0):
    input_lines = get_input_lines(inpath)
    if input_lines is None:
        return None
    sep_type = get_sep_type(input_lines)
    if sep_type is None:
        print("Error: Input file %s is not a SEP." % inpath, file=sys.stderr)
        sys.stdout.flush()
        return None
    elif sep_type not in SEP_TYPE_DISPATCH:
        print(
            ("Error: Unknown SEP type for input file %s: %s" % (inpath, sep_type)),
            file=sys.stderr,
        )
        sys.stdout.flush()
        return None
    elif SEP_TYPE_DISPATCH[sep_type] == None:
        sep_type_error(inpath, sep_type)
        return None
    outpath = os.path.splitext(inpath)[0] + ".html"
    if verbose:
        print(inpath, "(%s)" % sep_type, "->", outpath)
        sys.stdout.flush()
    outfile = open(outpath, "w", encoding="utf-8")
    SEP_TYPE_DISPATCH[sep_type](inpath, input_lines, outfile)
    outfile.close()
    os.chmod(outfile.name, 0o664)
    return outpath


def push_sep(htmlfiles, txtfiles, username, verbose, local=0):
    quiet = ""
    if local:
        if verbose:
            quiet = "-v"
        target = HDIR
        copy_cmd = "cp"
        chmod_cmd = "chmod"
    else:
        if not verbose:
            quiet = "-q"
        if username:
            username = username + "@"
        target = username + HOST + ":" + HDIR
        copy_cmd = "scp"
        chmod_cmd = "ssh %s%s chmod" % (username, HOST)
    files = htmlfiles[:]
    files.extend(txtfiles)
    files.append("style.css")
    files.append("sep.css")
    filelist = SPACE.join(files)
    rc = os.system("%s %s %s %s" % (copy_cmd, quiet, filelist, target))
    if rc:
        sys.exit(rc)


##    rc = os.system("%s 664 %s/*" % (chmod_cmd, HDIR))
##    if rc:
##        sys.exit(rc)


SEP_TYPE_DISPATCH = {"text/plain": fixfile, "text/x-rst": fix_rst_sep}
SEP_TYPE_MESSAGES = {}


def check_requirements():
    # Check Python:
    # This is pretty much covered by the __future__ imports...
    if sys.version_info < (2, 6, 0):
        SEP_TYPE_DISPATCH["text/plain"] = None
        SEP_TYPE_MESSAGES["text/plain"] = (
            'Python %s or better required for "%%(sep_type)s" SEP '
            "processing; %s present (%%(inpath)s)."
            % (REQUIRES["python"], sys.version.split()[0])
        )
    # Check Docutils:
    try:
        import docutils
    except ImportError:
        SEP_TYPE_DISPATCH["text/x-rst"] = None
        SEP_TYPE_MESSAGES["text/x-rst"] = (
            'Docutils not present for "%(sep_type)s" SEP file %(inpath)s.  '
            "See README.rst for installation."
        )
    else:
        installed = [int(part) for part in docutils.__version__.split(".")]
        required = [int(part) for part in REQUIRES["docutils"].split(".")]
        if installed < required:
            SEP_TYPE_DISPATCH["text/x-rst"] = None
            SEP_TYPE_MESSAGES["text/x-rst"] = (
                'Docutils must be reinstalled for "%%(sep_type)s" SEP '
                "processing (%%(inpath)s).  Version %s or better required; "
                "%s present.  See README.rst for installation."
                % (REQUIRES["docutils"], docutils.__version__)
            )


def sep_type_error(inpath, sep_type):
    print("Error: " + SEP_TYPE_MESSAGES[sep_type] % locals(), file=sys.stderr)
    sys.stdout.flush()


def browse_file(sep):
    import webbrowser

    file = find_sep(sep)
    if file.startswith("sep-") and file.endswith((".txt", ".rst")):
        file = file[:-3] + "html"
    file = os.path.abspath(file)
    url = "file:" + file
    webbrowser.open(url)


def browse_remote(sep):
    import webbrowser

    file = find_sep(sep)
    if file.startswith("sep-") and file.endswith((".txt", ".rst")):
        file = file[:-3] + "html"
    url = SEPDIRRUL + file
    webbrowser.open(url)


def main(argv=None):
    # defaults
    update = 0
    local = 0
    username = ""
    verbose = 1
    browse = 0

    check_requirements()

    if argv is None:
        argv = sys.argv[1:]

    try:
        opts, args = getopt.getopt(
            argv, "bilhqu:", ["browse", "install", "local", "help", "quiet", "user="]
        )
    except getopt.error as msg:
        usage(1, msg)

    for opt, arg in opts:
        if opt in ("-h", "--help"):
            usage(0)
        elif opt in ("-i", "--install"):
            update = 1
        elif opt in ("-l", "--local"):
            update = 1
            local = 1
        elif opt in ("-u", "--user"):
            username = arg
        elif opt in ("-q", "--quiet"):
            verbose = 0
        elif opt in ("-b", "--browse"):
            browse = 1

    if args:
        sep_list = []
        html = []
        for sep in args:
            file = find_sep(sep)
            sep_list.append(file)
            newfile = make_html(file, verbose=verbose)
            if newfile:
                html.append(newfile)
                if browse and not update:
                    browse_file(sep)
    else:
        # do them all
        sep_list = []
        html = []
        files = glob.glob("sep-*.txt") + glob.glob("sep-*.rst")
        files.sort()
        for file in files:
            sep_list.append(file)
            newfile = make_html(file, verbose=verbose)
            if newfile:
                html.append(newfile)
        if browse and not update:
            browse_file("0")

    if update:
        push_sep(html, sep_list, username, verbose, local=local)
        if browse:
            if args:
                for sep in args:
                    browse_remote(sep)
            else:
                browse_remote("0")


if __name__ == "__main__":
    main()

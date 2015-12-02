import os
import csv
import logging
import StringIO
import requests

import dialect
import encoding
from anycsv.csv_model import Table
from anycsv import io

DEFAULT_ENCODING='utf-8'
ENC_PRIORITY=['lib_chardet', 'header', 'default']

def reader(filename=None, url=None, content=None):
    logger = logging.getLogger(__name__)

    if not filename and not url and not content:
        raise IOError('No CSV input specified')

    meta = sniff_metadata(filename, url, content)
    table = Table(url=url, filename=filename)

    dialect = meta['dialect']
    if 'delimiter' in dialect:
        table.delimiter = dialect['delimiter']
    if 'quotechar' in dialect:
        table.quotechar = dialect['quotechar']

    table.encoding = meta['used_enc']

    if content:
        input = StringIO.StringIO(content)
    elif filename and os.path.exists(filename):
        input = open(filename, 'rU')
    elif url:
        input = requests.get(url, stream=True).iter_lines()
    else:
        raise IOError('No CSV input specified')

    if table.encoding and ('utf-8' in table.encoding or 'utf8' in table.encoding):
        table.csvReader = UnicodeReader(input,
                                        delimiter=table.delimiter,
                                        quotechar=table.quotechar)
    else:
        table.csvReader = EncodedCsvReader(input,
                                     encoding=table.encoding,
                                     delimiter=table.delimiter,
                                     quotechar=table.quotechar)

    table.columns = len(table.csvReader.next())
    input.seek(0)
    return table


def sniff_metadata(fName= None, url=None, content=None, header=None, sniffLines=100):
    logger = logging.getLogger(__name__)
    id = url if url is not None else fName

    if not any([fName,url]) and not any([content, header]):
        #we need at least one of the three, so return empty results
        return {}

    if not any([content, header]) and any([fName, url]):
        res = io.getContentAndHeader(fName=fName, url=url, download_dir="/tmp/", max_lines=sniffLines)
        content, header = res['content'], res['header']

    logger.debug('(%s) Extracting CSV meta data ', id)
    meta = extract_csv_meta(header=header, content=content)
    logger.debug("(%s) Meta %s ", id, meta)

    return meta


def extract_csv_meta(header, fName=None, content=None, id=''):
    logger = logging.getLogger(__name__)

    results = {'used_enc':None,
               'enc': encoding.guessEncoding(content, header),
               'dialect':{}}

    content_encoded = None
    status="META "
    c_enc = None
    for k in ENC_PRIORITY:
        #we try to use the different encodings
        try:
            if k in results['enc'] and results['enc'][k]['encoding'] is not None:
                content_encoded = content.decode(encoding=results['enc'][k]['encoding'])
                c_enc = results['enc'][k]['encoding']
                status+=" encoding"
                break
        except Exception as e:
            logger.debug('(%s) ERROR Tried %s encoding: %s', results['enc'][k]['encoding'],id, e)
    if content_encoded:
        results['used_enc'] = c_enc
        try:
            results['dialect'] = dialect.guessDialect(content_encoded)
            status+=" dialect"
        except Exception as e:
            logger.warning('(%s)  %s',id, e.message)
            results['dialect']={}
    else:
        try:
            results['dialect'] = dialect.guessDialect(content)
            status+=" dialect"
        except Exception as e:
            logger.warning('(%s) Cannot guess the dialect: %s',id, e.message)
            results['dialect']={}

    if fName:
        results['charset'] = encoding.get_charset(fName)

    logger.info("(%s) %s", id,status)
    return results


class CsvReader:

    def __init__(self, f, reader, encoding):
        self.f = f
        self.reader = reader
        self.encoding = encoding
        self._start_line = 0
        self.line_num = 0

    def __iter__(self):
        return self

    def seek_line(self, line_number):
        if line_number < self.line_num:
            self.f.seek(0)
            self.line_num = 0
        self._start_line = line_number

    def _next(self):
        while self._start_line > self.line_num:
            self.reader.next()
            self.line_num += 1
        row = self.reader.next()
        self.line_num += 1
        return row


class EncodedCsvReader(CsvReader):
    def __init__(self, f, encoding="utf-8-sig", delimiter="\t", quotechar="'", **kwds):
        if not quotechar:
            quotechar = "'"
        if not encoding:
            encoding = 'utf-8-sig'
        if not delimiter:
            reader = csv.reader(f, quotechar=quotechar.encode('ascii'), **kwds)
        else:
            reader = csv.reader(f, delimiter=delimiter.encode('ascii'), quotechar=quotechar.encode('ascii'),
                                     **kwds)
        CsvReader.__init__(self, f, reader, encoding)

    def next(self):
        row = self._next()
        result = [unicode(s.decode(self.encoding)) for s in row]
        return result


class UnicodeReader(CsvReader):
    def __init__(self, f, delimiter="\t", quotechar="'", encoding='utf-8', errors='strict', **kwds):
        if not quotechar:
            quotechar = "'"
        if not encoding:
            encoding = 'utf-8'
        if not delimiter:
            reader = csv.reader(f, quotechar=quotechar.encode('ascii'), **kwds)
        else:
            reader = csv.reader(f, delimiter=delimiter.encode('ascii'), quotechar=quotechar.encode('ascii'),
                                     **kwds)
        self.encoding_errors = errors
        CsvReader.__init__(self, f, reader, encoding)

    def next(self):
        row = self._next()
        encoding = self.encoding
        encoding_errors = self.encoding_errors
        float_ = float
        unicode_ = unicode
        return [(value if isinstance(value, float_) else
                 unicode_(value, encoding, encoding_errors)) for value in row]
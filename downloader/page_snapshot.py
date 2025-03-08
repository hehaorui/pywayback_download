from io import BytesIO
import re
import datetime
import httpx
from warcio.warcwriter import WARCWriter
from warcio.statusandheaders import StatusAndHeaders
from warcio.recordloader import ArcWarcRecord
from email.utils import parsedate

http_status_text = {
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    307: 'Temporary Redirect',
    308: 'Permanent Redirect',
}

ISO_DT = "%Y-%m-%dT%H:%M:%SZ"

def datetime_to_iso_date(the_datetime):
    """
    >>> datetime_to_iso_date(datetime.datetime(2013, 12, 26, 10, 11, 12))
    '2013-12-26T10:11:12Z'
    """
    return the_datetime.strftime(ISO_DT)

def http_date_to_datetime(string):
    """
    >>> http_date_to_datetime('Thu, 26 Dec 2013 09:50:10 GMT')
    datetime.datetime(2013, 12, 26, 9, 50, 10)
    """
    return datetime.datetime(*parsedate(string)[:6])

class PageSnapshot:
  def __init__(self, resp=None, index_record=None):
    self.resp: httpx.Response = resp
    self.index_record: dict = index_record


  def buildWarcRecord(self)->ArcWarcRecord:
    if not self.resp:
      raise ValueError("No response object assigned to this PageSnapshot")
    
    reason_phrase = self.resp.reason_phrase
    status_code = self.resp.status_code

    # handle the mismatch between the status code in index_record and the actual status code
    if self.index_record and "statuscode" in self.index_record:
      if str(self.index_record["statuscode"]) != str(self.resp.status_code):
        if self.resp.status_code == 302 and self.index_record["status_code"].starswith("3"):
          status_code = int(self.index_record["status_code"])
          if status_code in http_status_text:
            reason_phrase = http_status_text[status_code]

    
    http_headers = []
    http_date = None
    for k, v in self.resp.headers.items():
      kl = k.lower()
      if kl.startswith('x-archive-orig-date'):
          http_date = v
      if kl.startswith('x-archive-orig-'):
          k = k[len('x-archive-orig-'):]
          http_headers.append((k, v))
      elif kl == 'content-type':
          http_headers.append(('Content-Type', v))
      elif kl == 'location':
          v = 'http'+v.split('/http', 1)[1]
          http_headers.append((k, v))
      else:
          if not kl.startswith('x-archive-'):
              k = 'X-Archive-' + k
          http_headers.append((k, v))

    http_headers = StatusAndHeaders(str(status_code)+" "+reason_phrase, http_headers, 'HTTP/1.1')

    warc_headers_dict = {
      "WARC-Creation-Date": datetime_to_iso_date(datetime.datetime.now(datetime.UTC)),
    }

    if self.index_record and self.index_record.get("original"):
      if self.index_record.get("original") != str(self.resp.request.url):
        warc_headers_dict["WARC-Source-URI"] = str(self.resp.request.url)

    if http_date:
      warc_headers_dict["WARC-Date"] = datetime_to_iso_date(http_date_to_datetime(http_date))

    content_bytes = self.resp.content

    warc_writer = WARCWriter(None)
    return warc_writer.create_warc_record(self.get_original_url(), 
                                          'response', 
                                          payload=BytesIO(content_bytes), 
                                          warc_headers_dict=warc_headers_dict, 
                                          http_headers=http_headers)

  # generate the page's url in archive system
  # default to the IA's url
  def get_archive_url(self, base_url=None):
    if base_url==None:
      base_url = "https://web.archive.org/web/"
    if not self.index_record:
      raise Exception("No index_record specified")
    if not self.index_record["original"]:
      raise Exception("No original url specified in index_record")
    if not self.index_record["timestamp"]:
      raise Exception("No timestamp specified in index_record")

    #note that we need to append id_ after the timestamp to get the raw page
    return f"{base_url}{self.index_record['timestamp']}id_/{self.index_record['original']}"

  # genater the relative path to file tree root for storing the page
  # the path is inferred with a priority of 1.index_record, 2.IA's special response header, 
  # and 3.the requested url
  def get_tree_path(self):
    if self.resp == None and self.index_record == None:
      raise Exception("No response nor index_record specified")
    
    # frist check 'original' in index_record
    if self.index_record and "original" in self.index_record:
      original_url = httpx.URL(self.index_record["original"])
      timestamp = self.index_record["timestamp"]
    
    # check if it's snapshot fetched from IA
    elif self.resp.request.url.host == "web.archive.org" and \
          self.resp.request.url.path.startswith("/web/"):
        match = re.match(r"/web/(\d{14})/(.*)", self.resp.request.url.path)
        assert(match)
        original_url = httpx.URL(match.group(2))
        timestamp = match.group(1)
    
    # then it's an ordinary page
    else:
      original_url = httpx.URL(self.resp.request.url)
      timestamp = datetime.datetime.now().strftime("%Y%m%d%H%M%S")

    if original_url.path[-1] == "/" or original_url.path == "":
      path = original_url.path + "index.html"
    else:
      path = original_url.path
    return f"{original_url.host}/{timestamp}{path}"
  
  def get_original_url(self):
    if not self.index_record and not self.resp:
      raise Exception("No response nor index_record specified")
    
    if self.index_record and "original" in self.index_record:
      return self.index_record["original"]
    elif self.resp and self.resp.url.host == "web.archive.org" and \
          self.resp.url.path.startswith("/web/"):
      match = re.match(r"/web/\d{14}/(.*)", self.resp.url.path)
      assert(match)
      return match.group(2)
    else:
       return str(self.resp.request.url)

  def get_domain(self):
    if not self.index_record and not self.resp:
      raise Exception("No response nor index_record specified")
    
    if self.index_record and "original" in self.index_record:
      return str(httpx.URL(self.index_record["original"]).host)

    elif self.resp:
      return str(self.resp.url.host)
    

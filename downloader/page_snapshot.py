import re
import datetime
import httpx

class PageSnapshot:
  def __init__(self, resp=None, index_record=None):
    self.resp = resp
    self.index_record = index_record


  def buildWarcRecord(self):
    pass

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
    
    return f"{base_url}{self.index_record['timestamp']}/{self.index_record['original']}"

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

    
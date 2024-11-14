from enum import Enum
import httpx
import asyncio
import re

class MatchType(Enum):
  EXACT = 1
  PREFIX = 2
  HOST = 3
  DOMAIN = 4

class IndexFetcher:
  def __init__(self, base_url=None, gzip=True, 
               fl="timestamp,original,length", sleep_time=1):
    if base_url:
      self.base_url = base_url
    else:
      self.base_url = "http://web.archive.org/cdx/search/cdx/"
    self.gzip = gzip
    self.fl = fl
    self.sleep_time = sleep_time

    
    

  async def fetchIndex(self, url, fr=None, to=None, 
                       limit=100000, all=False, concurrency=10, 
                       matchType=MatchType.HOST, collapes="digest", retry=5):
    params = {
      "url": url,
      "output": "json",
      "gzip": "true" if self.gzip else "false",
      "limit": limit,
      "matchType": matchType.name.lower()
    }
    if collapes:
      params["collapse"] = collapes

    if all:
      params["filter"] = "statuscode:200"
      
    if fr:
      if re.match(r"\d{14}",fr)==None:
        raise Exception("Invalid date fromat at 'from', expected: 'YYYYMMDDHHMMSS'")
      params["from"] = fr
    if to:
      if re.match(r"\d{14}",to)==None:
        raise Exception("Invalid date fromat at 'to', expected: 'YYYYMMDDHHMMSS'")
      params["to"] = to
      
    async with httpx.AsyncClient(http2=True) as client:
      params["showNumPages"] = "true"
      try:
        json_data = (await client.get(self.base_url, params=params)).json()
      except Exception as e:
        errContent = str(e) if len(str(e))>0 else str(type(e))
        print(f"Failed to fetch the number index page for {url}: {errContent}")
        return []
      page_num = int(json_data[1][0])
      print(f"Found {page_num} pages of index for {url}, "
              f"now fetch after sleeping for {self.sleep_time}s...")
      await asyncio.sleep(self.sleep_time)
      
      params["showNumPages"] = "false"
      params["fl"] = self.fl
      self.total = page_num

      q = asyncio.Queue()
      for i in range(page_num):
        await q.put({"page": i, "retry": retry})
      
      concur = min(concurrency, page_num)   
      coros = [self.__fetcher_coroutine__(client, params, q) for _ in range(concur)]
      
      results = sum(await asyncio.gather(*coros), [])
      print(f"Fetched {len(results)} records for {url}")
      return results
        
  async def __fetcher_coroutine__(self, client, params, q):
    params = params.copy()
    results = []
    while not q.empty():
      item = await q.get()
      params["page"] = item["page"]
      try:
        data = (await client.get(self.base_url, params=params)).json()[1:]
        print(f"Fetched {len(data)} index at page {params["page"]+1}/{self.total}")
      except Exception as e:
        errContent = str(e) if len(str(e))>0 else str(type(e))
        if item["retry"] <= 0:
          print(f"Failed to fetch index at page ({params["page"]+1}/{self.total}): "
                f"{errContent}, aborting this page...")
        else:
          await q.put({"page": item["page"], "retry": item["retry"]-1})
          print(f"Failed to fetch index at page ({params["page"]+1}/{self.total}): "
                f"{errContent}, {item["retry"]} retries left")
        print(f"\tSleeping for {self.sleep_time}s before next request...")
        await asyncio.sleep(self.sleep_time)
        continue
      
      results += data
      print(f"\tSleeping for {self.sleep_time}s before next request...")
      await asyncio.sleep(self.sleep_time)
    return results
          
  
def main():
  fetcher = IndexFetcher(sleep_time=2)
  asyncio.run(fetcher.fetchIndex("www.cqu.edu.cn", concurrency=2, collapes=None))

if __name__ == "__main__":
  main()
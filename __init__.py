#!/bin/python
import asyncio
import warcio.warcwriter
from index.index_fetcher import IndexFetcher, MatchType
from downloader.downloader import Downloader, FileTreeWriter, MyWARCWriter

async def main():
  q = asyncio.Queue()
  idx_fetcher = IndexFetcher(sleep_time=10)
  # writer = FileTreeWriter(base_dir="./www.cqu.edu.cn/")
  with open("www.cqu.edu.cn.warc", "wb") as output:
    warcio_writer = warcio.warcwriter.WARCWriter(output, gzip=False)
    writer = MyWARCWriter(warciowriter=warcio_writer)
    downloader = Downloader(writer=writer)

    tsk_list = [idx_fetcher.fetchIndex("cqu.edu.cn", concurrency=1, out_queue=q, matchType=MatchType.DOMAIN), 
              downloader.download(q, concurrency=20, retry=20)]
    await asyncio.gather(*tsk_list)

if __name__ == "__main__":
  asyncio.run(main())

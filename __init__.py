#!/bin/python
from downloader.wayback_machine_parser import wayback_machine_mapper
from downloader.downloader import ListParser, download_from_json
def main():
  json_file = "./filelist.json"
  dir = "<path_to_save_downloaded_files>"
  download_from_json(json_file, thread_count=50, parser=ListParser(wayback_machine_mapper), dir=dir)

if __name__ == "__main__":
  main()
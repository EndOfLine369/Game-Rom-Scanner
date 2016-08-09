import sys              # getfilesystemencoding, getdefaultencoding
import os               # getcwd, listdir, path.basename, path.dirname, path.exists, path.isdir, path.isfile, path.join, path.relpath, path.splitext
import time             # strftime
import re               # sub, match, search
import unicodedata      # normalize
import tempfile         # NamedTemporaryFile
from lxml import etree  # fromstring
import zipfile          # ZipFile, is_zipfile
import string           # capwords
import Media            # Episode
import Utils            # SplitPath
import logging          # getLogger, Formatter, DEBUG, INFO
import logging.handlers # RotatingFileHandler
try:                 from urllib.request import urlopen # urlopen Python 3.0 and later
except ImportError:  from urllib2        import urlopen # urlopen Python 2.x #import urllib2 # urlopen

LOGGING_LEVEL = logging.INFO
LOG_FILENAME  = 'Plex Media Scanner (custom GameRS)'

DUMMY_VIDEO_URL      = 'https://github.com/EndOfLine369/Game-Rom-Scanner/blob/master/resources/video/GameRSDummyVideo.mp4?raw=true'
DUMMY_VIDEO_FILENAME = 'GameRSDummyVideo.mp4'
DUMMY_VIDEO_FILE     = ''

PLATFORM_EXTENSIONS_URL      = 'http://rawgit.com/EndOfLine369/Game-Rom-Scanner/master/resources/cfg/PlatformExtensions.xml'
PLATFORM_EXTENSIONS_FILENAME = 'GameRS-tmp-PlatformExtensions.xml'
PLATFORM_EXTENSIONS          = None

PLATFORM_FILE_SIGNATURES_URL      = 'http://rawgit.com/EndOfLine369/Game-Rom-Scanner/master/resources/cfg/PlatformSignatures.xml'
PLATFORM_FILE_SIGNATURES_FILENAME = 'GameRS-tmp-PlatformSignatures.xml'
PLATFORM_FILE_SIGNATURES          = None

CHARACTERS_MAP = {}

SEASON_MAPPING = {'A': 1,  'B': 2,  'C': 3,  'D': 4,  'E': 5,  'F': 6,  'G': 7,  'H': 8,  'I': 9,  'J': 10, 'K': 11, 'L': 12, 'M': 13, 
                  'N': 14, 'O': 15, 'P': 16, 'Q': 17, 'R': 18, 'S': 19, 'T': 20, 'U': 21, 'V': 22, 'W': 23, 'X': 24, 'Y': 25, 'Z': 26}

IGNORE_DIRS_RX  = ['@Recycle', '.@__thumb', 'lost\+found', '.AppleDouble','$Recycle.Bin', 'System Volume Information', 'Temporary Items', 'Network Trash Folder', 
                   '@eaDir', 'Extras', 'Samples?', 'bonus', '.*bonus disc.*', 'trailers?', '.*_UNPACK_.*', '.*_FAILED_.*', 'misc', '_Misc']
IGNORE_FILES_RX = ['[-\._ ]sample', 'sample[-\._ ]', '-Recap\.', 'OST', 'soundtrack', 'Thumbs.db', '.plexignore']                                                       # Skipped files (samples, trailers)                                                          
FILTER_CHARS    = "\\/:*?<>|~;_."  # Windows file naming limitations + "~-,._" + ';' as plex cut title at this for the agent

#########################################################################################################
RootLogger,     RootHandler,     RootFormatting     = logging.getLogger('main'),           None, logging.Formatter('%(asctime)-15s - GAMERS : %(levelname)s - %(message)s')
FileListLogger, FileListHandler, FileListFormatting = logging.getLogger('FileListLogger'), None, logging.Formatter('%(message)s')
RootLogger.setLevel(logging.DEBUG); FileListLogger.setLevel(logging.DEBUG)
#print("Loggers: %s" % logging.Logger.manager.loggerDict)  #print("Logger->Handlers: 'main': %s" % Log.handlers)
Log, LogFileList = RootLogger, FileListLogger.info

def set_logging(instance, filename):
  global RootLogger, RootHandler, FileListLogger, FileListHandler
  logger, handler, formatting, backup_count = [RootLogger, RootHandler, RootFormatting, 9] if instance=="Root" else [FileListLogger, FileListHandler, FileListFormatting, 1]
  #2016-07-24 00:54:23 CWD: /share/CACHEDEV1_DATA/.qpkg/PlexMediaServer
  log_paths = [ os.path.join(os.getcwd(), 'Library', 'Plex Media Server', 'Logs'),
                os.path.join(os.getcwd(), 'Library', 'Application Support', 'Plex Media Server', 'Logs'),
                os.path.join(os.getcwd(), 'Plex Media Server', 'Logs') ]
  for log_path in log_paths:
    if os.path.exists(log_path): break
  else:
    #None of the pre-defined log paths were matched so log to the temp directory
    tmp_file = tempfile.NamedTemporaryFile(); tmp_filename = tmp_file.name; tmp_file.close()#; del tmp_file
    log_path = os.path.dirname(tmp_filename)
  print("log_path: %s, filename: %s" % (log_path, filename))
  print("log file: %s" % os.path.join(log_path, filename))
  if handler: logger.removeHandler(handler); print("Handler removed: %s" % handler)
  handler = logging.handlers.RotatingFileHandler(os.path.join(log_path, filename), maxBytes=10*1024*1024, backupCount=backup_count)    #handler = logging.FileHandler(os.path.join(LOG_PATH, filename), mode)
  handler.setFormatter(formatting)
  handler.setLevel(LOGGING_LEVEL)
  logger.addHandler(handler)
  if instance=="Root":  RootHandler     = handler
  else:                 FileListHandler = handler

set_logging("Root", LOG_FILENAME + '.log')

#########################################################################################################
def pull_url_file(url, filename):
  tmp_file   = tempfile.NamedTemporaryFile(delete=False); tmp_filename = tmp_file.name; tmp_file.close()
  local_file = tmp_filename.replace(os.path.basename(tmp_filename), filename)
  try:
    if not os.path.exists(local_file) or int(time.time() - os.path.getmtime(local_file)) > 86400:
      Log.info("%s: '%s' from '%s'" % ("Updating" if os.path.exists(local_file) else "Creating", local_file, url))
      with open(tmp_filename, 'w') as pe_file:  pe_file.write( urlopen( url ).read() )
      os.rename(tmp_filename, local_file)
    else:  Log.info("Using existing: '%s'" % local_file); del tmp_file
    return local_file
  except Exception as e:  Log.error("Error downloading file from GitHub '%s', Exception: '%s'" % (url, e)); raise e; return None

#########################################################################################################
def file_into_xml(local_file):
  try:
    with open(local_file, 'r') as fh:  content = etree.fromstring( fh.read() )
    return content
  except Exception as e:  Log.error("Error parsing file from local '%s', Exception: '%s'" % (url, e)); raise e; return None

#########################################################################################################
def pull_extensions():
  global PLATFORM_EXTENSIONS, PLATFORM_FILE_SIGNATURES
  pe_content = file_into_xml( pull_url_file(PLATFORM_EXTENSIONS_URL, PLATFORM_EXTENSIONS_FILENAME) )
  if pe_content is not None:
    PLATFORM_EXTENSIONS = {}
    for pf in pe_content.xpath("/platform-extensions/type/platform"):
      PLATFORM_EXTENSIONS[pf.get("name")] = [pf.get("year"), [ext2 for ext in pf.iter("extensions") if ext.text for ext2 in ext.text.split(",")]]
  else: raise Exception("Failed to load the PLATFORM_EXTENSIONS values")
  
  ps_content = file_into_xml( pull_url_file(PLATFORM_FILE_SIGNATURES_URL, PLATFORM_FILE_SIGNATURES_FILENAME) )
  if ps_content is not None:
    PLATFORM_FILE_SIGNATURES = {}
    for pf in ps_content.xpath("/platform-signarures/platform"):
      PLATFORM_FILE_SIGNATURES[pf.get("name")] = {}
      for sig in pf.iter("signarure"): PLATFORM_FILE_SIGNATURES[pf.get("name")][sig.text] = int(sig.get("address"))
  else: raise Exception("Failed to load the PLATFORM_FILE_SIGNATURES values")
  
  Log.info("PLATFORM_EXTENSIONS: %s"      % PLATFORM_EXTENSIONS)    
  Log.info("PLATFORM_FILE_SIGNATURES: %s" % PLATFORM_FILE_SIGNATURES)    

### Return number of bytes of Unicode characters ########################################################
def unicodeLen (char):                                           # count consecutive 1 bits since it represents the byte numbers-1, less than 1 consecutive bit (128) is 1 byte , less than 23 bytes is 1
  for x in range(1,6):                                           # start at 1, 6 times 
    if ord(char) < 256-pow(2, 7-x)+(2 if x==6 else 0): return x  # 256-2pow(x) with x(7->0) = 128 192 224 240 248 252 254 255 = 1 to 8 bits at 1 from the left, 256-2pow(7-x) starts form left

### Decode string back to Unicode ###   #Unicodize in utils?? #fixEncoding in unicodehelper
def encodeASCII(string, language=None): #from Unicodize and plex scanner and other sources
  if string=="": return ""
  ranges = [ {"from": ord(u"\u3300"), "to": ord(u"\u33ff")}, {"from": ord(u"\ufe30"), "to": ord(u"\ufe4f")}, {"from": ord(u"\uf900"), "to": ord(u"\ufaff")},  # compatibility ideographs
             {"from": ord(u"\u30a0"), "to": ord(u"\u30ff")}, {"from": ord(u"\u2e80"), "to": ord(u"\u2eff")},                                                  # Japanese Kana    # cjk radicals supplement
             {"from": ord(u"\u4e00"), "to": ord(u"\u9fff")}, {"from": ord(u"\u3400"), "to": ord(u"\u4dbf")}]                                                  # windows: TypeError: ord() expected a character, but string of length 2 found #{"from": ord(u"\U00020000"), "to": ord(u"\U0002a6df")}, #{"from": ord(u"\U0002a700"), "to": ord(u"\U0002b73f")}, #{"from": ord(u"\U0002b740"), "to": ord(u"\U0002b81f")}, #{"from": ord(u"\U0002b820"), "to": ord(u"\U0002ceaf")}, # included as of Unicode 8.0                             #{"from": ord(u"\U0002F800"), "to": ord(u"\U0002fa1f")}  # compatibility ideographs
  encodings, encoding = ['iso8859-1', 'utf-16', 'utf-16be', 'utf-8'], ord(string[0])                                                                          #
  if 0 <= encoding < len(encodings):  string = string[1:].decode('cp949') if encoding == 0 and language == 'ko' else string[1:].decode(encodings[encoding])   # If we're dealing with a particular language, we might want to try another code page.
  if sys.getdefaultencoding() not in encodings:
    try:     string = string.decode(sys.getdefaultencoding())
    except:  pass
  if not sys.getfilesystemencoding()==sys.getdefaultencoding():
    try:     string = string.decode(sys.getfilesystemencoding())
    except:  pass
  string = string.strip('\0')
  try:       string = unicodedata.normalize('NFKD', string)    # Unicode  to ascii conversion to corect most characters automatically
  except:    pass
  try:       string = re.sub(RE_UNICODE_CONTROL, '', string)   # Strip control characters.
  except:    pass
  try:       string = string.encode('ascii', 'replace')        # Encode into Ascii
  except:    pass
  original_string, string, i = string, list(string), 0
  while i < len(string):                                       ### loop through unicode and replace special chars with spaces then map if found ###
    if ord(string[i])<128:  i = i+1
    else: #non ascii char
      char, char2, char3, char_len = 0, "", [], unicodeLen(string[i])
      for x in range(0, char_len):
        char = 256*char + ord(string[i+x]); char2 += string[i+x]; char3.append(string[i+x])
        if not x==0: string[i] += string[i+x]; string[i+x]=''
      try:    asian_language = any([mapping["from"] <= ord("".join(char3).decode('utf8')) <= mapping["to"] for mapping in ranges])
      except: asian_language = False
      if char in CHARACTERS_MAP:  string[i]=CHARACTERS_MAP.get( char )
      elif not asian_language:    Log.warning("*Character missing in CHARACTERS_MAP: %d:'%s'  , #'%s' %s, string: '%s'" % (char, char2, char2, char3, original_string))
      i += char_len
  return ''.join(string)

### Allow to display ints even if equal to None at times ################################################
def clean_string(string, no_parenthesis=False, no_dash=False):
  if not string: return ""                                                                                                                                    # if empty return empty string
  if no_parenthesis:                                                                                                                                          # delete parts between parenthesis if needed
    while re.match(".*\([^\(\)]*?\).*", string):                 string = re.sub(r'\([^\(\)]*?\)', ' ', string)                                               #   support imbricated parrenthesis like: "Cyborg 009 - The Cyborg Soldier ((Cyborg) 009 (2001))"
  if re.search("(\[|\]|\{|\})", string):                         string = re.sub("(\[|\]|\{|\})", "", re.sub(r'[\[\{](?![0-9]{1,3}[\]\}]).*?[\]\}]', ' ', string))  # remove "[xxx]" groups but ep numbers inside brackets as Plex cleanup keep inside () but not inside [] #look behind: (?<=S) < position < look forward: (?!S)
  string = encodeASCII(string)                                                                                                                                # Translate them
  string = re.sub(r'(?P<a>[^0-9Ssv])(?P<b>[0-9]{1,3})\.(?P<c>[0-9]{1,2})(?P<d>[^0-9])', '\g<a>\g<b>DoNoTfIlTeR\g<c>\g<d>', string)                            # Used to create a non-filterable special ep number (EX: 13.5 -> 13DoNoTfIlTeR5) # Restricvted to max 999.99 # Does not start with a season/special char 'S|s' (s2.03) or a version char 'v' (v1.2)
  for char, subst in zip(list(FILTER_CHARS), [" " for x in range(len(FILTER_CHARS))]) + [("`", "'"), ("(", " ( "), (")", " ) ")]:                             # remove leftover parenthesis (work with code a bit above)
    if char in string:                                           string = string.replace(char, subst)                                                         # translate anidb apostrophes into normal ones #s = s.replace('&', 'and')
  string = string.replace("DoNoTfIlTeR", '.')                                                                                                                 # Replace 13DoNoTfIlTeR5 into 13.5 back
  if re.match(".*?[\(\[\{]?[0-9a-fA-F]{8}[\[\)\}]?.*", string):  string = re.sub('[0-9a-fA-F]{8}', ' ', string)                                               # CRCs removal
  if re.search("[0-9]{3,4} ?[Xx] ?[0-9]{3,4}", string):          string = re.sub('[0-9]{3,4} ?[Xx] ?[0-9]{3,4}', ' ', string)                                 # Video size ratio removal
  if string.endswith(", The"):                                   string = "The " + ''.join( string.split(", The", 1) )                                        # ", The" is rellocated in front
  if string.endswith(", A"  ):                                   string = "A "   + ''.join( string.split(", A"  , 1) )                                        # ", A"   is rellocated in front
  if no_dash:                                                    string = re.sub("-", " ", string)                                                            # replace the dash '-'
  string = re.sub(r'\([-Xx]?\)', '', re.sub(r'\( *(?P<internal>[^\(\)]*?) *\)', '(\g<internal>)', string))                                                    # Remove internal spaces in parenthesis then remove empty parenthesis
  string = " ".join([word for word in filter(None, string.split())]).strip()                                                                                  # remove multiple spaces
  for rx in ("-"):                                               string = string[len(rx):   ].strip() if string.startswith(rx)       else string              # In python 2.2.3: string = string.strip(string, " -_") #if string.startswith(("-")): string=string[1:]
  for rx in ("-", "- copy"):                                     string = string[ :-len(rx) ].strip() if string.lower().endswith(rx) else string              # In python 2.2.3: string = string.strip(string, " -_")
  return string

### Add files into Plex database ########################################################################
def add_into_plex(mediaList, file, ext, platform, title, year, season, ep):
  Log.debug("add_into_plex: file='%s', platform='%s', season='%s', ep='%s', title='%s', year='%s'" % (file, platform, season, ep, title, year) )
  if len(platform) == 0: Log.warning("platform: '%s', s%02de%03d, file: '%s' has platform empty, report logs to dev ASAP" % (platform, season, ep, file))
  else:
    tv_show = Media.Episode(platform, season, ep, title, int(year) if year.isdigit() else None)
    tv_show.parts.append(file)
    tv_show.parts.append(DUMMY_VIDEO_FILE)
    mediaList.append(tv_show)
    Log.info("\"%s\" s%04de%03d \"%s\" \"%s\" (%s)" % (platform, season, ep, os.path.basename(file), title, ext))
    Log.debug(tv_show)

#########################################################################################################
def Scan(path, files, mediaList, subdirs, language=None, root=None, **kwargs): #get called for root and each root folder
  if not path:
    set_logging("Root", LOG_FILENAME + '.log')
    Log.info("".ljust(157, '=')); Log.info(("=== Root: \"%s\",  Launched: %s" % (root, time.strftime("%Y-%m-%d %H:%M:%S "))).ljust(157, '='))
    set_logging("FileList", LOG_FILENAME + ' - filelist ' + os.path.basename(root) + ".log")
    LogFileList("".ljust(157, '=')); LogFileList("==== Starting File Scan (root:%s) ====" % root); LogFileList("".ljust(157, '='))
    pull_extensions()
    global DUMMY_VIDEO_FILE
    DUMMY_VIDEO_FILE = pull_url_file(DUMMY_VIDEO_URL, DUMMY_VIDEO_FILENAME)

  Log.info("".ljust(157, '=')); Log.info("Scanner call - root: '%s', path: '%s', dirs: '%d', files: '%d'" % (root, path, len(subdirs), len(files))); Log.info("".ljust(157, '='))
  for file   in files:    LogFileList(file)                     # Dump to the log all files passed
  for subdir in subdirs:  Log.debug("Directories: %s" % subdir) # Dump to the log all subdirectories passed

  if not path:                    # root call so start with an empty list 
    Log.info("Setting blank 'plex_entries' & 'platform_season_counts' variables")
    plex_entries, platform_season_counts = [], {}
    for platform in PLATFORM_EXTENSIONS.keys():  platform_season_counts[platform] = [0 for num in range(1, 28)]
  elif 'plex_entries' in kwargs:  # non-root call but 'plex_entries' exists from a manual subdir Scan call
    Log.info("Using passed 'plex_entries' & 'platform_season_counts' variables")
    plex_entries, platform_season_counts = kwargs['plex_entries'], kwargs['platform_season_counts']
  else:                           # non-root call but from Plex
    Log.info("Skipping Plex's non-root sub directory scan");  return

  for subdir in subdirs:
    for rx in IGNORE_DIRS_RX:
      if re.match(rx, os.path.basename(subdir), re.IGNORECASE):  subdirs.remove(subdir);  Log.info("\"%s\" match IGNORE_DIRS_RX: \"%s\"" % (subdir, rx));  break  #skip dirs to be ignored

  files_to_remove, extensions = [], [extension for value in PLATFORM_EXTENSIONS.values() for extension in value[1]]
  for file in files:
    ext = os.path.splitext(file)[1].lstrip('.').lower()
    if ext in extensions or zipfile.is_zipfile(file):
      for rx in IGNORE_FILES_RX:                                          # Filter trailers and sample files
        if re.match(rx, file, re.IGNORECASE):  Log.info("File: '%s' match IGNORE_FILES_RX: '%s'" % (file, rx)); files_to_remove.append(file);  break
    else:  Log.info("file: '%s', ext: '%s' not in PLATFORM_EXTENSIONS" % (file, ext));  files_to_remove.append(file);  continue
  for file in files_to_remove:  files.remove(file)

  Log.info("Files Left: %s" % len(files))
  for file in files:
    Log.debug("Processing: %s" % file)
    try:
      title         = " ".join(string.capwords(part, '-') for part in clean_string(os.path.splitext(os.path.basename(file))[0], True).split())  # Split the file name and extension & cap each word
      ext, ext_list = os.path.splitext(file)[1].lstrip('.').lower(), []                                                                         # Split the file name and extension.

      found_platform_ids = [key for key in PLATFORM_EXTENSIONS if ext in PLATFORM_EXTENSIONS[key][1]]  # Check if the extension is our dictionary
      platform_id = found_platform_ids[0] if found_platform_ids else ""

      if platform_id and platform_id == 'Unknown Platform':
        Log.debug("Platform is defined as 'Unknown Platform' so running file signature checks")
        with open(file, "r+b") as fh:
          for pf in PLATFORM_FILE_SIGNATURES:  # Loop through possible file signatures
            for sig in PLATFORM_FILE_SIGNATURES[pf]:
              Log.debug("Checking for platform '%s' using signature '%s'" % (pf, sig))
              fh.seek(PLATFORM_FILE_SIGNATURES[pf][sig], 0)
              if '0x' + fh.read((len(sig) - 2)/2).encode('hex') == sig:  platform_id = pf;  break
            else:  continue
            break

      if not platform_id and zipfile.is_zipfile(file):  # This could be a rom zipped up, or it could be a random zip file.
        Log.debug("File is a zipfile so checking each internal file's extension")
        zfile = zipfile.ZipFile(file)                   # We should actually check inside the zip itself.
        for zzfile in zfile.namelist():
          Log.debug("Checking internal file '%s'" % zzfile)
          #zztitle = " ".join(string.capwords(part, '-') for part in clean_string(os.path.splitext(os.path.basename(zzfile))[0], True).split())  # Split the file name and extension & cap each word
          zzext   = os.path.splitext(zzfile)[1].lstrip('.').lower()
          found_platform_ids = [key for key in PLATFORM_EXTENSIONS if zzext in PLATFORM_EXTENSIONS[key][1]]  # Check if the extension is our dictionary
          if found_platform_ids:  platform_id, ext = found_platform_ids[0], zzext;  break  #title = zztitle
          else:  ext_list.append(zzext)

        # If there's only one rom file, and it ends in a few specific extensions...
        if platform_id == 'Unknown Platform' and len(zfile.namelist()) == 1:
          Log.debug("Platform is defined as 'Unknown Platform' so running file signature checks")
          filecontents = zfile.read(zfile.namelist()[0])
          zzext = os.path.splitext(zfile.namelist()[0])[1].lstrip('.').lower()
          for pf in PLATFORM_FILE_SIGNATURES:
            for sig in PLATFORM_FILE_SIGNATURES[pf]:
              Log.debug("Checking for platform '%s' using signature '%s'" % (pf, sig))
              if '0x' + filecontents[PLATFORM_FILE_SIGNATURES[pf][sig]:(PLATFORM_FILE_SIGNATURES[pf][sig] + ((len(sig) - 2)/2))].encode('hex') == sig:  platform_id, ext = pf, zzext;  break
            else:  continue
            break
      else:  ext_list.append(ext)

      if not platform_id: platform_id = "Unknown Platform";  Log.warning("No mapped extensions found for: %s" % ext_list)
      year   = PLATFORM_EXTENSIONS[platform_id][0]  if platform_id                               else ""
      season = SEASON_MAPPING[title[0].upper()]     if title[0].upper() in SEASON_MAPPING.keys() else 27
      platform_season_counts[platform_id][season-1] += 1
      ep     = platform_season_counts[platform_id][season-1]

      plex_entry = [file, ext, platform_id, title, year, season, ep]
      Log.info("Plex Entry: %s" % plex_entry)
      plex_entries.append(plex_entry)
    except Exception as e:
      Log.error("Error on: %s, Exception: %s" % (file, e))

  Log.info("Done")

  for subdir in subdirs:
    subdir_files, subdir_subdirs = [], []
    for file in os.listdir(subdir):
      file_abs = os.path.join(subdir,file)
      if   os.path.isfile(file_abs):  subdir_files.append(file_abs)
      elif os.path.isdir(file_abs):   subdir_subdirs.append(file_abs)
    Scan(os.path.relpath(subdir,root), sorted(subdir_files), [], sorted(subdir_subdirs), root=root, plex_entries=plex_entries, platform_season_counts=platform_season_counts)

  if path: return
  else:
    Log.info("".ljust(157, '=')); Log.info("Sorting then adding in all files into Plex"); Log.info("".ljust(157, '='))
    plex_entries = sorted(plex_entries, key=lambda x: "%s s%04de%03d" % (x[2], x[5], x[6]))
    for entry in plex_entries:  add_into_plex(mediaList, entry[0], entry[1], entry[2], entry[3], entry[4], entry[5], entry[6])
    for entry in mediaList:     Log.debug("'mediaList' Entry: %s" % entry)

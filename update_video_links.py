from pathlib import Path
import sys
import re
import requests
from  urllib.parse import urlparse, urlunparse
import os
import PyPDF2
import json
import datetime
import copy
import tkinter as tk
from tkinter import simpledialog
from tkinter import ttk
from bs4 import BeautifulSoup

ADD_LEARNING_MATERIALS = False
UPDATE_SYLLABUS = True
CONSTANTS_FILE = "constants.json"




# Open the file and read the contents
try:
  with open(CONSTANTS_FILE, 'r') as f:
    constants = json.load(f)
except Exception as e:
  tk.messagebox.showerror(message=f"Problem loading constants.json. Ask hallie for a copy of constants.json and put it in this folder.\n{e}")
# save the api key
try:
  api_token = constants["apiToken"]
  api_url = constants["apiUrl"]

  drive_url = None
  if "driveUrl" in constants:
    drive_url = constants["driveUrl"]

  account_id = 169877
except Exception as e:
  tk.messagebox.showerror(message=f"It looks like your constants file is missing some values. Ask hallie for a current copy of the constants.json file.\n{e}")


# Authorize the request.
headers = {"Authorization": f"Bearer {api_token}" }

def main():
  course_id = 0
  old_course_id = 0


  #course = response.json()

  if len(sys.argv) > 1:
   course_id = sys.argv[1]
  else:
   course_id = tk.simpledialog.askinteger("What Course?", "Enter the course_id of the new course (cut the number out of the url and paste here)")


  url = f"{api_url}/courses/{course_id}"
  print(url)
  response = requests.get(url, headers=headers)
  if response.status_code != 200:
    tk.messagebox.showinfo("report", f"Course not found.\n{response.text}")
    exit()
  course = response.json()

  if not old_course_id or old_course_id == 0:
    code = course["course_code"].split("_")[1][0:7]
    print("Code", code)
    response = requests.get(f"{api_url}/accounts/{account_id}/courses", headers=headers, params = {"search_term" : f"DEV_{code}"} )
    courses = response.json()

    for course in courses:
      print(course["course_code"])
    if len(courses) > 0:
      old_course_id = courses[0]["id"]
      print("Old course found", old_course_id, courses[0]["course_code"])

  if len(sys.argv) > 2:
    if  "lm" in sys.argv:
      update_learning_materials(course_id)
    if "syllabus" in sys.argv:
      update_syllabus_and_overview(course_id, old_course_id)
    if "overviews" in sys.argv:
      update_weekly_overviews(course_id, old_course_id)

    if "assignment" in sys.argv:
      update_weekly_overviews(course_id, old_course_id)
      id_index = sys.argv('assignment') + 1
      if not len(sys.argv) > id_index:
        print("Error: Assignment id not provided")
        exit()

      assignment_id = sys.argv[id_index]

    if "assignments" in sys.argv:
      create_missing_assignments(course_id, old_course_id)
      align_assignments(course_id, old_course_id)

  else:
    if tk.messagebox.askyesno(message="Do you want to update learning materials?"):
      update_learning_materials(course_id)

    if tk.messagebox.askyesno(message="Do you want to update the syllabus and course overview?"):
      update_syllabus_and_overview(course_id, old_course_id) 

    if tk.messagebox.askyesno(message="Do you want to try to update the weekly overviews?"):
      update_weekly_overviews(course_id, old_course_id)       


def get_modules(course_id):
  url = f"{api_url}/courses/{course_id}/modules?include[]=items&include[]=content_details"
  response = requests.get(url, headers=headers)
  return response.json()
  
def create_missing_assignments(course_id, old_course_id):
  modules = get_modules(course_id)
  old_modules = get_modules(old_course_id)

  gallery_discussion = None

  for old_module in old_modules:
    items = old_module["items"]

    #skip non-week modules
    number = get_old_module_number(old_module)
    name = get_old_module_title(old_module)
    if not number:
      continue

    module = find_new_module_by_number(number, modules)

    #save off the gallery discussion
    print(number)
    if number == "1":
      gallery_discussion_template = next( filter( lambda item: "Gallery Discussion" in item["title"], module["items"]))
      print (gallery_discussion_template)

    create_missing_assignments_in_module(module, old_module, course_id, old_course_id, gallery_discussion_template)



def create_missing_assignments_in_module(module, old_module, course_id, old_course_id, gallery_discussion_template):

  old_assignments = list ( filter( lambda item: item["type"] == "Assignment", old_module["items"]) )
  assignments = list( filter( lambda item: item["type"] == "Assignment", module["items"]) )
  difference = len(old_assignments)  - len(assignments)
  if difference > 0:
    added_items = True

    #duplicate the first assignment as many times as it takes to get parity between assignments
    for _ in range(0, difference):
      duplicate_item(course_id, assignments[0], module)

  #get discussions and pull out gallery discussions to handle differently
  old_discussions = list ( filter( lambda item: item["type"] == "Discussion", old_module["items"]) )
  old_gallery_discussions = remove_gallery_discussions(old_discussions)

  discussions = list( filter( lambda item: item["type"] == "Discussion", module["items"]) )
  gallery_discussions = remove_gallery_discussions(discussions)

  #add discussions if there is disparity
  difference = len(old_discussions)  - len(discussions)
  if difference > 0:
    added_items = True

    #duplicate the first discussion as many times as it takes to get parity between assignments
    for _ in range(0, difference):
      duplicate_item(course_id, discussions[0], module)

  difference = len(old_gallery_discussions)  - len(gallery_discussions)
  if difference > 0:
    added_items = True

    #duplicate the first discussion as many times as it takes to get parity between assignments
    for _ in range(0, difference):
      duplicate_item(course_id, gallery_discussion_template, module)

def get_old_file_url_to_new_file_lookup_table(course_id, old_course_id):

    files = get_paged_data(f"{api_url}/courses/{course_id}/files?per_page=100")
    old_files = get_paged_data(f"{api_url}/courses/{old_course_id}/files?per_page=100")


    old_file_url_lookup_table = dict()
    for old_file in old_files:
      #match files by name and size
      file = list( filter( lambda a: old_file["filename"] == a["filename"], files) )[0]
      old_file_url_lookup_table[old_file["id"]] = file

    return old_file_url_lookup_table  

def get_assignments_lookup_table(modules, old_modules):
  old_id_to_id_lut = dict()

  for old_module in old_modules:
    items = old_module["items"]

    #skip non-week modules
    number = get_old_module_number(old_module)
    name = get_old_module_title(old_module)
    if not number:
      continue

    module = find_new_module_by_number(number, modules)
  
    old_assignments = list ( filter( lambda item: item["type"] == "Assignment", old_module["items"]) )
    assignments = list( filter( lambda item: item["type"] == "Assignment", module["items"]) )
  
    old_discussions = list ( filter( lambda item: item["type"] == "Discussion", old_module["items"]) )
    old_gallery_discussions = remove_gallery_discussions(old_discussions)

    discussions = list( filter( lambda item: item["type"] == "Discussion", module["items"]) )
    gallery_discussions = remove_gallery_discussions(discussions)
 
    populate_lookup_table(old_id_to_id_lut, old_assignments, assignments)
    populate_lookup_table(old_id_to_id_lut, old_discussions, discussions)
    populate_lookup_table(old_id_to_id_lut, old_gallery_discussions, gallery_discussions)

  return old_id_to_id_lut

def align_assignments(course_id, old_course_id):
  modules = get_modules(course_id)
  old_modules = get_modules(old_course_id)
  old_id_to_id_lut = dict()

  file_lut = get_old_file_url_to_new_file_lookup_table(course_id, old_course_id)
  assignments_lut = get_assignments_lookup_table(modules, old_modules)

  old_rubric_url = f"{api_url}/courses/{old_course_id}/rubrics"
  rubric_url = f"{api_url}/courses/{course_id}/rubrics"

  old_rubric_response = requests.get(old_rubric_url, headers=headers)
  rubric_response = requests.get(rubric_url, headers=headers)
   
  assert old_rubric_response.ok, "Can't get old course rubrics"
  assert rubric_response.ok, "Can't get new course rubrics"

  old_rubrics = old_rubric_response.json()
  rubrics = rubric_response.json()

  print(json.dumps(rubrics, indent=4))

  for old_module in old_modules:
    items = old_module["items"]

    #skip non-week modules
    number = get_old_module_number(old_module)
    name = get_old_module_title(old_module)
    if not number:
      continue

    module = find_new_module_by_number(number, modules)
  
    old_assignments = list ( filter( lambda item: item["type"] == "Assignment", old_module["items"]) )
    assignments = list( filter( lambda item: item["type"] == "Assignment", module["items"]) )
  
    old_discussions = list ( filter( lambda item: item["type"] == "Discussion", old_module["items"]) )
    old_gallery_discussions = remove_gallery_discussions(old_discussions)

    discussions = list( filter( lambda item: item["type"] == "Discussion", module["items"]) )
    gallery_discussions = remove_gallery_discussions(discussions)

    def handle_gallery_discussion(item, old_item):
      old_body = old_item["assignment"]["description"]
      old_soup = BeautifulSoup(old_body)
      print(old_soup.prettify())

    handle_items(gallery_discussions, old_gallery_discussions, handle_gallery_discussion)




def handle_items(items, old_items, handle_func, course_id = None, old_course_id = None):
  i = 0
  for old_item in old_items:
    item = items[i]
    print(f"Parsing {old_item['title']} into {item['title']}")

    url = item["url"]
    old_url = old_item["url"]
    response = requests.get(url, headers=headers)
    assert response.ok, json.dumps(response.json(), indent=2)

    old_response = requests.get(url, headers=headers)
    assert old_response.ok, json.dumps(response.json(), indent=2)

    item = response.json()
    old_item = response.json()


    handle_func(item, old_item)

    i = i + 1

def populate_lookup_table(lut, old_items, items):
  i = 0
  if len(old_items) > len(items):
    raise Exception("Number of items in new module is fewer than items in old module")
  for old_item in old_items:
    item = items[i]
    i = i + 1
    lut[old_item["url"]] = item["url"]

def remove_gallery_discussions(discussions, remove_introduction = True):
  gallery_discussions = []
  for discussion in discussions:
    #just throw away introductions
    if remove_introduction and "Introduction" in discussion["title"]:
      discussions.remove(discussion)

    if "Gallery" in discussion["title"]:
      gallery_discussions.append(discussion)
      discussions.remove(discussion)
  return gallery_discussions

def duplicate_item(course_id, item, module=None):
  item_id =  item["url"].split('/')[-1] #grab the resource id off the end of the url
  type_ = item["type"]
  print(f"Duplicating assignment {item_id}")

  if type_ == "Assignment":
    url = f"{api_url}/courses/{course_id}/assignments/{item_id}/duplicate"
  elif type_ == "Discussion":
    url = f"{api_url}/courses/{course_id}/discussion_topics/{item_id}/duplicate"

  print(url)
  response = requests.post(url, headers=headers)
  if not response.ok:
    print(response)
    raise response.raise_for_status()
  item = response.json()

  print(f"Adding {type_} {item['title']} to module {module['name']}")
  url = f"{api_url}/courses/{course_id}/modules/{module['id']}/items"
  print(url)
  payload = {
    "module_item[title]" : item["title"],
    "module_item[content_id]" : item["id"],
    "module_item[type]" : type_,
    "module_item[indent]" : 1,
    "module_item[position]" : 999
    }

  print(payload)
  response = requests.post(url, headers=headers, data = payload)
  if not response.ok:
    print(response.json())
    raise response.raise_for_status()

  print(response.json())
  return item

def get_old_module_number(module):  
    title_words = module["name"].split(" ")
    if ( "week" in title_words[0].lower()):
      return title_words[1]
    return False

def get_old_module_title(module):  
    #if the module name is "Week X" return the name of the subheader
    title_words = module["name"].split(" ")
    if ( "week" in title_words[0].lower()):
      return module["items"][0]["title"]

    #if the module name is not "Week X" just return the full module name
    return module["name"]

def find_new_module_by_number(number, modules):
 return next( filter ( lambda module: f"Module {number}" in module["name"], modules) )

def update_weekly_overviews(course_id, old_course_id):
  url = f"{api_url}/courses/{old_course_id}/modules?include[]=items&include[]=content_details"
  response = requests.get(url, headers=headers)
  print(response.status_code)
  old_modules = response.json()

  url = f"{api_url}/courses/{course_id}/modules?include[]=items&include[]=content_details"
  response = requests.get(url, headers=headers)
  print(response.status_code)
  modules = response.json()

  for old_module in old_modules:
    print(old_module["name"])
    title_words = old_module["name"].split(" ")
    items = old_module["items"]
    if ("week" in title_words[0].lower()):


      i = int(title_words[1])
      module_name = old_module ['items'][0]["title"]

      module = next( filter ( lambda module: f"Module {i}" in module["name"], modules) )

      set_module_title(course_id, module["id"], f"Module {i} - {module_name}".title())
  
      old_overview_page_info = next(filter(lambda item: "overview" in item["title"].lower(), items))
      old_lo_page_info = next(filter(lambda item: "learning objectives" in item["title"].lower(), items))

      old_overview_page = get_page_by_url (old_overview_page_info["url"])
      old_lo_page = get_page_by_url (old_lo_page_info["url"])
      overview_page = get_page_by_url (f"{api_url}/courses/{course_id}/pages/week-{i}-overview")

      old_overview_soup = BeautifulSoup(old_overview_page["body"], 'lxml')
      old_lo_soup = BeautifulSoup(old_lo_page["body"], 'lxml')

      #grab the list of learning objectives from the page
      learning_objectives = old_lo_soup.find('ul')
      if not learning_objectives:
        learning_objectives = old_lo_soup.find("ol")

      learning_objectives = learning_objectives.prettify()

      description_box = old_overview_soup.find("div", class_="column")
      description = "\n".join( 
        map(lambda tag: str(tag), list(description_box.children))
      )

      new_page_body = new_overview_page_html(overview_page["body"], module_name, description, learning_objectives)

      response = requests.put(f'{api_url}/courses/{course_id}/pages/{overview_page["url"]}', 
        headers = headers,
        data = {
          "wiki_page[body]" : new_page_body
        }
      )  
     
def set_module_title(course_id, module_id, title ):
  url = f"{api_url}/courses/{course_id}/modules/{module_id}"
  print(url)
  response = requests.put(url, 
    headers = headers,
    data = {
      "module[name]" : title
    }
  )  
  print(response.text)

def new_overview_page_html(overview_page_body, title, description, learning_objectives):
  body = overview_page_body 
  soup = BeautifulSoup(body, "lxml")
  contents = soup.find_all("div", class_ = "content")
  contents[0].string = "[Insert text]"
  contents[1].string = "[insert weekly objectives, bulleted list]"

  body = soup.prettify()

  body = re.sub('\[title of week\]', f"{title}", body)
  body = re.sub('\[Insert.*text\]', f"{description}", body)
  body = re.sub('\[insert weekly objectives, bulleted list\]', f"{learning_objectives}", body)
  return body

def get_page_by_url(url):
  response = requests.get(url, headers=headers)
  page = response.json()
  return page

def get_file_url_by_name(course_id, file_search):
  #get syllabus banner url
  url = f"{api_url}/courses/{course_id}/files"
  response = requests.get(url, headers=headers, params={"search_term" : file_search})
  files = response.json()
  if len(files) > 0:
    return files[0]["url"]
  return false

def update_syllabus_and_overview(course_id, old_course_id):
  old_page = get_syllabus(old_course_id)
  new_page = get_syllabus(course_id)



  syllabus_banner_url = get_file_url_by_name(course_id, "Module 1 banner (7)")


  is_course_grad = not old_page.find(string="Poor, but Passing")

  title = find_syllabus_title(old_page)
  description_paras = get_section(old_page, "Course Description:")
  learning_objectives_paras = get_section(old_page, "Course Outcomes:")
  textbook_paras = get_section(old_page, "Textbook:")
  week_1_preview = get_week_1_preview(course_id)

  term = "DE8W01.08.24" if is_course_grad else "DE/HL-24-Jan"
  dates = "January 8 - March 3" if is_course_grad  else "January 15 - February 18" 

  try:
    with open("syllabus_template.html", 'r') as f:
      template = f.read()
      text = template.format(
        banner_url = syllabus_banner_url,
        course_id = course_id,
        term_code = term,
        term_dates = dates,
        course_outcomes = "\n".join(map(lambda p: p.prettify(), learning_objectives_paras)),
        course_description = "\n".join(map(lambda p: p.prettify(), description_paras)),
        course_title = title,
        week_1_learning_materials = "\n".join(map(lambda p: p.prettify(), week_1_preview)),
        textbook = "\n".join(map(lambda p: p.prettify(), textbook_paras)),
      )
  except Exception as e:
    tk.messagebox.showerror(message="syllabus_template.html missing. Please download the latests from drive.")
    exit()

  #update the new syllabus

  submit_soup = BeautifulSoup(text, "lxml")


  if is_course_grad:
    for el in list ( submit_soup.find_all("p", class_ = "undergrad") ):
      el.decompose()
    for el in list ( submit_soup.find_all("div", class_ = "undergrad") ):
      el.decompose()
  else:
    for el in list ( submit_soup.find_all("p", class_ = "grad") ):
      el.decompose()
    for el in list ( submit_soup.find_all("div", class_ = "grad") ):
      el.decompose()

  response = requests.put(f'{api_url}/courses/{course_id}', 
    headers = headers,
    data = {
      "course[syllabus_body]" : submit_soup.prettify()
    }
  )


  print(response.status_code)


  url = f"{api_url}/courses/{course_id}/modules?include[]=items&include[]=content_details"
  response = requests.get(url, headers=headers)
  print(response.status_code)
  modules = response.json()

  overview_module = next(filter(lambda module: module["position"] == 1, modules))
  page_id  = overview_module['items'][0]['page_url']
  print(page_id)
  print(overview_module ['items'][0])
  url = f"{api_url}/courses/{course_id}/pages/{page_id}"

  response = requests.get(url, headers=headers)
  print(response.status_code)
  overview_page = response.json()

  overview_html = overview_page["body"]
  og_ov_soup = BeautifulSoup(overview_html, "lxml").body
  print(og_ov_soup)
  overview_banner_img = og_ov_soup.find("img", width=750)
  print(overview_banner_img)
  overview_banner_url = overview_banner_img["src"]

  #get assignment groups
  url = f"{api_url}/courses/{old_course_id}/assignment_groups"
  response = requests.get(url, headers=headers)
  groups = response.json()
  assignment_categories = groups

  #assignment weight text
  table_body = ""
  for assignment in assignment_categories:
    assignment["description"] = ""
    if "discussion" in assignment["name"].lower():
      assignment["description"] = 'Initial posts due by 3AM ET Thursday night, responses due by 3AM ET Monday night - unless otherwise noted.'

    if "assignment" in assignment["name"].lower():
      assignment["description"] = "Due by the end of the week in which they're assigned."

    table_body = table_body + f'''
    <tr style="height: 167px;">
      <td>{assignment["name"].title()}</td>
      <td>{assignment["description"]}</td>
      <td>{int(assignment["group_weight"])}%</td>
    </tr>
    '''

  try:
    with open("overview_template.html", 'r') as f:
      template = f.read()
      text = template.format(
        banner_url = overview_banner_url,
        course_id = course_id,
        course_outcomes = "\n".join(map(lambda p: p.prettify(), learning_objectives_paras)),
        course_description = "\n".join(map(lambda p: p.prettify(), description_paras)),
        table_body = table_body,
        textbook = "\n".join(map(lambda p: p.prettify(), textbook_paras)),
      )
  except Exception as e:
    tk.messagebox.showerror(message="overview_template.html missing. Please download the latests from drive.")
    exit()




  submit_soup = BeautifulSoup(text, "lxml")

  response = requests.put(f'{api_url}/courses/{course_id}/pages/course-overview', 
    headers = headers,
    data = {
      "wiki_page[body]" : submit_soup.prettify()
    }
  )  
   #set_week_1_preview(new_page, get_week_1_preview(course_id))
  #set_syllabus_description(new_page, description)
  #set_syllabus_learning_objectives(new_page, learning_objectives)
  #set_syllabus_dates(new_page, start_date, end_date, term_code)
  #update_grading(new_page, is_course_grad)


  #update the new overview

  #get existing course overview



def get_syllabus(course_id):
  url = f"{api_url}/courses/{course_id}?include[]=syllabus_body"
  response = requests.get(url, headers=headers)
  content = response.json()
  print(content)
  return BeautifulSoup(content["syllabus_body"], "lxml")

def find_syllabus_title(soup):
  header = soup.find("strong", string=re.compile("course number and title", re.IGNORECASE))
  title_p = header.find_parent("p")
  header.decompose()
  return title_p.text

def get_section(soup, header_string):
  header = soup.find("h4", string=header_string)
  if not header:
    header = soup.find("strong", string=header_string).parent
  print(header)
  paragraphs = []
  el =  header.find_next_sibling()
  print(el.name)
  while el and el.name != "h4":
    paragraphs.append(el)
    el = el.find_next_sibling()
  return paragraphs


def replace_content(soup, header_string, list_of_new_contents):
  container = soup.find("h2", string=header_string).parent

  #remove existing paras
  for el in container.find_all("p"):
    el.decompose()
  for el in list_of_new_contents:
    container.append(el)

  print(container)


#https://codereview.stackexchange.com/questions/272811/converting-a-youtube-embed-link-to-a-regular-link-in-python
def convert_to_watch_url(embed_url: str) -> str:
    """Convert a YouTube embed URL into a watch URL."""

    scheme, netloc, path, params, query, fragment = urlparse(embed_url)
    video_id, path = Path(path).stem, '/watch'
    return urlunparse((scheme, netloc, path, params, f'v={video_id}', fragment))


def get_week_1_preview(course_id):

    old_lm_url = f"{api_url}/courses/{course_id}/pages/week_1_learning_materials-2"


    lm_response = requests.get(old_lm_url, headers=headers)

    print(lm_response)

    lm_page = lm_response.json()
    lm_soup = BeautifulSoup(lm_page["body"], "lxml")

    h4 = lm_soup.find("h4")
    learning_materials =  get_section(lm_soup, "Please read and watch the following materials:")


    iframe = lm_soup.find("iframe")
    youtube_iframe_source = iframe["src"]
    links = lm_soup.find_all("a")
    transcripts = []
    slides = []
    for link in links:
      if 'ranscript' in link.text:
        transcripts.append(link)
      if 'lides' in link.text:
        slides.append(link)

    temp_soup = BeautifulSoup(f"<li><a href={convert_to_watch_url(youtube_iframe_source)}>Week 1 Lecture</a><ul></ul></li>", "lxml")
    list_ = temp_soup.find("ul")
    for transcript in transcripts:
      li = temp_soup.new_tag("li")
      a = temp_soup.new_tag("a")
      a.string = "transcript"
      a["href"] = transcript["href"]
      li.append(a)
      list_.append(li)
    for slide in slides:
      li = temp_soup.new_tag("li")
      a = temp_soup.new_tag("a")
      a.string = "slides"
      a["href"] = slide["href"]
      li.append(a)
      list_.append(li)

    learning_materials[0].insert( 0, temp_soup.html.body.li )
    return learning_materials


def update_learning_materials(course_id):
  for i in range(1,9):

    #get the latest page matching the learning materials search
    url = f"{api_url}/courses/{course_id}/pages/"
    response = requests.get(url, headers=headers, data={
      "sort" : "created_at",
      "search_term" : f"Week {i} Learning Materials"
      })
    if not response.ok:
      raise Exception(response.json())


    if len(response.json()) < 2:
      continue
    old_lm_url = response.json()[-1]["url"]

    old_url = f"{api_url}/courses/{course_id}/pages/{old_lm_url}"
    new_url = f"{api_url}/courses/{course_id}/pages/week_{i}_learning_materials"
    print(f"copying from {old_url} to {new_url}")

    old_page_response = requests.get(old_url, headers=headers)
    if old_page_response.status_code != 200:
      continue
    old_page = old_page_response.json()

    new_page_response = requests.get(new_url, headers=headers)
    new_page = new_page_response.json()

    old_soup = BeautifulSoup(old_page["body"])
    new_soup = BeautifulSoup (new_page["body"])
    
    #handle youtube links
    old_iframe = old_soup.find("iframe")
    new_iframe = new_soup.find("iframe")
    youtube_iframe_source = old_iframe["src"]
    new_iframe["src"] = youtube_iframe_source


    old_header = old_soup.find("h4")
    learning_materials = list(old_header.next_siblings)
    
    #handle transcripts
    transcripts_and_slides = old_soup.find_all("div", {'class':"column"})[1].find_all("a")

    buttons = new_soup.find_all("p", { "class" : "cbt-button"})
    slides_button = None
    transcript_button = None

    for button in buttons:
      if button.find("a", string=re.compile("Slides",re.IGNORECASE)):
        slides_button = button.find("a", string=re.compile("Slides",re.IGNORECASE))
      if button.find("a", text=re.compile("Transcript", re.IGNORECASE)):
        transcript_button = button.find("a", string=re.compile("Transcript", re.IGNORECASE))

    slides_count = 0
    transcripts_count = 0
    old_transcript_button = None
    for element in transcripts_and_slides:

      if element.find(string=re.compile("Transcript", re.IGNORECASE)):
        if (transcripts_count > 0):
          old_button = transcript_button
          old_button["body"] = f"Transcript {transcripts_count}"
          button_container = copy.copy(old_button.parent)
          old_button.parent.parent.append(button_container)
          transcript_button = button_container.find('a')
          transcript_button["body"] = f"Transcript {transcripts_count + 1}"

        #replace link
        transcript_button["href"] = element["href"]
        transcripts_count = transcripts_count + 1

      if element.find(string=re.compile("Slides", re.IGNORECASE)):
        if (slides_count > 0):
          old_button = slides_button
          old_button["body"] = f"Slides {slides_count}"
          button_container = copy.copy(old_button.parent)
          old_button.parent.parent.append(button_container)
          slides_button = button_container.find('a')
          slides_button["body"] = f"Slides {slides_count + 1}"

        #replace link
        slides_button["href"] = element["href"]
        slides_count = slides_count + 1



    #handle learning materials
    accordion = new_soup.find("div", class_="cbt-accordion-container")


    #make a new accordion and just all the learning materials into it IF this accordion is a template
    if accordion.find(string="[Title for first category of LMs]"):
      print("adding Learning Materials")
      new_content = copy.copy(accordion)
      accordion.parent.append(new_content)
      content = new_content.find("div", class_="cbt-answer")
      for el in learning_materials:
        content.append(el)
        print(content)
        print(el)



    #save changes
    response = requests.put(f'{api_url}/courses/{course_id}/pages/{new_page["page_id"]}', 
      headers = headers,
      data = {
        "wiki_page[body]" : new_soup.prettify()
      }
    )
    print(new_page["title"],response.status_code)

def get_paged_data(url, headers=headers):
  response = requests.get(url, headers=headers)
  out = response.json()
  next_page_link = "!"
  while len(next_page_link) != 0:
      pagination_links = response.headers["Link"].split(",")
      for link in pagination_links:
        if 'next' in link:
          next_page_link = link.split(";")[0].split("<")[1].split(">")[0]
          print(next_page_link)
          response = requests.get(next_page_link, headers=headers)
          out = out + response.json()
          break
        else:
          next_page_link = ""  
  print(len(out))

  return out

main()
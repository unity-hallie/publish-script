import unittest
from typing import List

import publish_script
from publish_script import Term, Course
import requests

CONSTANTS_FILE = 'constants_test.json'

CONSTANTS = publish_script.load_constants(CONSTANTS_FILE, publish_script)


accounts = requests.get(f'{publish_script.API_URL}/accounts', headers=publish_script.HEADERS).json()

API_URL = publish_script.API_URL
ACCOUNT_ID = publish_script.ACCOUNT_ID
ROOT_ACCOUNT_ID = publish_script.ROOT_ACCOUNT_ID
TEST_COURSE_CODE: str = 'TEST000'
TEST_TERM_CODE = 'DE/HL-24-Jan'

print(publish_script.API_URL)
assert('test' in publish_script.API_URL)


def get_test_course():
    return Course.get_by_code(f'BP_{TEST_COURSE_CODE}')


def get_test_section():
    return Course.get_by_code(f'24-Jan_{TEST_COURSE_CODE}')


def get_item_names(items):
    # also work for modules
    if 'items' in items:
        items = items['items']
    return list(map(lambda a: a['name'] if 'name' in a else a['title'], items))


def flatten_modules(modules: list):
    out = []
    return [item for module in modules for item in module['items']]


class TestMisc(unittest.TestCase):
    def test_flatten_module(self):
        course = Course.get_by_code('DEV_' + TEST_COURSE_CODE)
        modules = publish_script.get_modules(course['id'])
        flattened_modules = flatten_modules(modules)
        print(flattened_modules)
        alt_flattened_modules = []
        for module in modules:
            alt_flattened_modules = alt_flattened_modules + module['items']
        flat_module_size = len(flattened_modules)

        print(get_item_names(alt_flattened_modules))
        self.assertEqual(
            len(flattened_modules), len(alt_flattened_modules),
            f'Not the right size: {flat_module_size} items across modules')
        self.assertEqual(
            ','.join(get_item_names(flattened_modules)),
            ','.join(get_item_names(alt_flattened_modules)),
            f'flattened_modules={flattened_modules}')


class TestCourseResetAndImport(unittest.TestCase):
    """
    Tests for getting course reset and importing
    Can take a long time to run
    """

    def test_reset(self):
        course = Course.get_by_code(f'BP_{TEST_COURSE_CODE}')
        self.assertIsNotNone(course, "Can't Find Test Course by code")

        original_course_id = course['id']
        course.unset_as_blueprint()
        reply_course = publish_script.reset_course(course)
        self.assertNotEqual(original_course_id, reply_course['id'], "Course id has not been changed on reset")

        course = Course.get_by_code(f'BP_{TEST_COURSE_CODE}')
        self.assertIsNotNone(course, "Course does not exist")
        self.assertFalse(publish_script.get_modules(int(course['id'])), "Course contains modules after reset")

        self.assertEqual(reply_course._canvas_data, course._canvas_data, f"Reset course is not the same as searched for course - {reply_course['id']}, {course['id']}")

    def test_import_dev(self):
        self.maxDiff = None
        bp_course = Course.get_by_code(f'BP_{TEST_COURSE_CODE}')
        publish_script.import_dev_course(bp_course)
        bp_course = Course.get_by_code(f'BP_{TEST_COURSE_CODE}', params={'include[]': 'syllabus_body'})
        dev_course = Course.get_by_code(f'DEV_{TEST_COURSE_CODE}', params={'include[]': 'syllabus_body'})
        self.assertEqual(
            len(bp_course['syllabus_body']), len(dev_course['syllabus_body']), "Course syllabi do not mach")

        bp_modules = publish_script.get_modules(int(bp_course.id))
        dev_modules = publish_script.get_modules(int(bp_course.id))
        self.assertEqual(
            get_item_names(flatten_modules(bp_modules)),
            get_item_names(flatten_modules(dev_modules)),
            f"BP modules do not match dev modules.")

    def test_unset_blueprint(self):
        course = Course.get_by_code(f'BP_{TEST_COURSE_CODE}')
        self.assertIsNotNone(course, "Can't Find Test Course by code")
        course.unset_as_blueprint()
        self.assertFalse(course.is_blueprint, "Course is a blueprint")

    def test_set_blueprint(self):
        course = Course.get_by_code(f'BP_{TEST_COURSE_CODE}')
        self.assertIsNotNone(course, "Can't Find Test Course by code")
        course.set_as_blueprint()
        self.assertTrue(course.is_blueprint, "Course is not blueprint")
        print(course['blueprint_restrictions'])
        self.assertEqual(
            course['blueprint_restrictions'],
            {
                'content': True,
                'points': True,
                'due_dates': True,
                'availability_dates': True,
            },
            "Restrictions not properly set on course")


class TestProfilePages(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self):
        pass

    def test_download_faculty_pages(self):
        bios = publish_script.get_faculty_pages(True)
        self.assertGreater(len(bios), 10, "No Bios Found")
        self.assertListEqual(bios, publish_script.get_faculty_pages(), msg="Bios not returning properly")

    def test_get_instructor_page(self):
        section = get_test_section()
        user = publish_script.get_canvas_instructor(section['id'])
        pages = publish_script.get_instructor_page(user)
        pages_from_name = publish_script.get_instructor_page(user['name'])
        self.assertEqual(len(pages), 1, msg="Returned more than one instructor page")
        self.assertListEqual(pages, pages_from_name, msg="Returned different pages for instructor pages")

    def test_get_course_profile(self):
        section = get_test_section()
        pages = publish_script.get_faculty_pages()
        profile = publish_script.get_course_profile(section, pages)
        user = publish_script.get_canvas_instructor(section['id'])

        self.assertEqual(profile.user['name'], user['name'], msg="Profile names do not match")


class TestLocking(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        course = get_test_course()
        modules = publish_script.get_modules(course['id'])
        if len(modules) == 0:
            publish_script.import_dev_course(course)

    async def test_lock(self):
        course = get_test_course()
        course.set_as_blueprint()
        self.assertIsNotNone(course, "Can't Find Test Course by code")
        self.assertTrue(await publish_script.lock_module_items_async(course), "locking did not succeed")

    def test_lock_sync(self):
        course = get_test_course()
        course.set_as_blueprint()
        self.assertIsNotNone(course, "Can't Find Test Course by code")
        self.assertTrue(publish_script.lock_module_items(course), "locking did not succeed")


class TestCourse(unittest.TestCase):

    def test_course_properties(self):
        code = f"BP_{TEST_COURSE_CODE}"
        course: Course = Course.get_by_code(code)
        self.assertEqual(course['name'], course._canvas_data['name'], "course['name'] does not match its data")

    def test_get_course(self):
        code = f"BP_{TEST_COURSE_CODE}"
        course: Course = Course.get_by_code(code)
        course_by_id: Course = Course.get_by_id(course.id)
        # The test course code is a stub; we should be able to get all the prefix matching versions:
        # BP, DEV, and any Sections
        courses: List[Course] = Course.get_by_code(TEST_COURSE_CODE, return_list=True)
        self.assertIsNotNone(course)
        self.assertEqual(course.course_code, code, "course codes by id and code do not match")
        self.assertEqual(course_by_id.id, course.id, "ids of course by id and by code do not match")
        self.assertEqual(course_by_id['name'], course['name'], "names of course by id and by code do not match")
        self.assertGreater(len(courses), 2, "Not enough courses found")


class TestTerm(unittest.TestCase):
    def setUp(self):
        pass

    def tearDown(self) -> None:
        pass

    def test_load_by_code(self):
        term = Term.get_by_code(TEST_TERM_CODE)
        self.assertIsNotNone(term, "Term not found for code{}".format(TEST_TERM_CODE))
        self.assertEqual(term['name'], TEST_TERM_CODE, "Term code doesn't match")


import unittest
import tempfile
import filecmp
import os
import inspect

import config
import coco

TEST_ROOT=os.path.join(os.path.dirname(__file__), 'tests')

class CompilerTests(unittest.TestCase):
    """All tests here are driven by the data under tests/, which includes
    source and expected build output.
    """

    # We could just glob the files, but this way we get nicer output from
    # Python.  A bit debatable whether it's worth it.
    
    def test_hello(self):                 self._t()
    def test_catch(self):                 self._t()
    def test_catch_two(self):             self._t()
    def test_catch_multiple_except(self): self._t()
    def test_activity(self):              self._t()
    def test_break(self):                 self._t()
    def test_retry(self):                 self._t()
    def test_if(self):                    self._t()
    def test_lift(self):                  self._t()
    def test_wait(self):                  self._t()

    def _t(self):
        """Run test according to the name of our caller; if we're called by test_hello
        we run the src/tests/hello test.

        """
        self._test_1("_".join(inspect.currentframe().f_back.f_code.co_name.split('_')[1:]))

    def _assert_dcmp_equal(self, dcmp):
        """Assert (recursively) that two directories have the same contents
        (i.e. it asserts that the set of files is the same and that the
        contents of the files match).

        """

        if len(dcmp.diff_files) > 0:
            fs = dcmp.diff_files
            print("Different files: %s." % (", ".join(fs)))
            # print diffs
            for f in fs:
                left = os.path.join(dcmp.left, f)
                right = os.path.join(dcmp.right, f)
                os.system("diff %s %s" % (left, right))                
        
        self.assertEqual(len(dcmp.left_only), 0)
        self.assertEqual(len(dcmp.right_only), 0)
        self.assertEqual(len(dcmp.diff_files), 0)
        self.assertEqual(len(dcmp.common_funny), 0)
        self.assertEqual(len(dcmp.funny_files), 0)
        for sub_dcmp in dcmp.subdirs.values():
            self._assert_dcmp_equal(sub_dcmp)

    def _assert_dir_equal(self, expected, actual):
        dcmp = filecmp.dircmp(expected, actual, ignore=[])
        self._assert_dcmp_equal(dcmp)
        
    def _test_1(self, testRelPath):
        """Run one test. 

        This compiles the source under testPath/*.py, and asserts that
        the output matches testPath/build/

        """

        testPath = os.path.join(TEST_ROOT, testRelPath)
        
        # ls testPath/*.py | head -1
        srcFile = [f for f in os.listdir(testPath) if f.endswith('.py')][0]
        src = os.path.join(testPath, srcFile)

        expectedBuild = os.path.join(testPath, "build")
        
        # build into tmp dir, compare results
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg = config.Config()
            cfg.set('from_file', True)
            cfg.set('output_dir', tmpdir)

            # compile
            coco.coco(cfg, src)

            # compare
            self._assert_dir_equal(expectedBuild, tmpdir)


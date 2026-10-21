"""Project boundaries must isolate outputs and preserve protected inputs."""
import tempfile
import unittest
from pathlib import Path

from workflow_triage.repository import ArtifactRepository


class RepositoryTests(unittest.TestCase):
    def test_independent_project_locks_and_output_cleanup(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            projects = []
            for name in ('one', 'two'):
                project = root/name
                project.mkdir()
                repo = ArtifactRepository(project)
                repo.dist.mkdir()
                (repo.dist/'stale.txt').write_text(name)
                (repo.root/'input.txt').write_text('preserve')
                projects.append(repo)
            one, two = projects
            with one.locked(), two.locked():
                one.reset_outputs()
                with self.assertRaises(BlockingIOError):
                    with one.locked():
                        pass
            self.assertFalse((one.dist/'stale.txt').exists())
            self.assertEqual((two.dist/'stale.txt').read_text(), 'two')
            self.assertEqual((one.root/'input.txt').read_text(), 'preserve')

    def test_output_symlink_is_never_cleaned(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            outside = root/'outside'
            outside.mkdir()
            (outside/'keep.txt').write_text('preserve')
            project = root/'project'
            project.mkdir()
            repo = ArtifactRepository(project)
            repo.dist.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlinked'):
                repo.reset_outputs()
            self.assertEqual((outside/'keep.txt').read_text(), 'preserve')


if __name__ == '__main__':
    unittest.main()

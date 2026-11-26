import datetime, os, sys, unittest
from unittest import mock
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import post_ig as P

K = P.KYIV
def item(i, t, st='pending', pub=None):
    x = {'id': i, 'тип': 'carousel', 'час': t, 'підпис': f'текст {i}', 'urls': ['u1', 'u2'], 'стан': st}
    if pub: x['опубліковано'] = pub
    return x


class Due(unittest.TestCase):
    now = datetime.datetime(2026, 11, 20, 12, 0, tzinfo=K)

    def test_oldest_overdue_first(self):
        q = [item('b', '2026-11-19T12:30:00+02:00'), item('a', '2026-11-18T09:00:00+02:00'), item('c', '2026-11-21T09:00:00+02:00')]
        self.assertEqual(P.due(q, self.now)['id'], 'a')

    def test_one_per_kyiv_day(self):
        q = [item('a', '2026-11-18T09:00:00+02:00', 'done', '2026-11-20T09:01:00+02:00'), item('b', '2026-11-19T12:30:00+02:00')]
        self.assertIsNone(P.due(q, self.now))

    def test_future_not_due(self):
        self.assertIsNone(P.due([item('c', '2026-11-21T09:00:00+02:00')], self.now))

    def test_error_items_skipped(self):
        self.assertIsNone(P.due([item('a', '2026-11-18T09:00:00+02:00', 'error')], self.now))


class Publish(unittest.TestCase):
    def setUp(self):
        os.environ['IG_TOKEN'] = 't'; os.environ['IG_USER_ID'] = '42'
        self.saved = []; P.save = lambda items: self.saved.append([dict(x) for x in items])

    def test_duplicate_guard_marks_done_without_publishing(self):
        x = item('a', '2026-11-18T09:00:00+02:00')
        with mock.patch.object(P, 'api', return_value={'data': [{'id': '9', 'caption': 'текст a', 'permalink': 'https://i/p/9'}]}) as api, \
             mock.patch.object(P, 'container') as c:
            P.publish([x], x)
        c.assert_not_called(); self.assertEqual(x['стан'], 'done'); self.assertEqual(x['media_id'], '9')

    def test_state_saved_right_after_publish(self):
        x = item('a', '2026-11-18T09:00:00+02:00')
        calls = []
        def api(path, data=None, method=None, params=None):
            calls.append(path)
            if path == '42/media': return {'data': []}
            if path.endswith('media_publish'): return {'id': '77'}
            return {'permalink': 'https://i/p/77'}
        with mock.patch.object(P, 'api', side_effect=api), mock.patch.object(P, 'container', return_value='c1'):
            P.publish([x], x)
        self.assertEqual(self.saved[0][0]['стан'], 'done'); self.assertEqual(x['посилання'], 'https://i/p/77')
        self.assertIn('42/media_publish', calls)



class FbMirror(unittest.TestCase):
    def test_failure_is_recorded_not_raised(self):
        x = item('a', '2026-11-18T09:00:00+02:00', 'done')
        with mock.patch.object(P, 'fb_post', side_effect=RuntimeError('boom')), mock.patch.object(P, 'save'):
            P.fb_mirror([x], x)
        self.assertEqual(x['fb_помилка'], 'boom'); self.assertNotIn('fb_id', x)

    def test_not_posted_twice(self):
        x = dict(item('a', '2026-11-18T09:00:00+02:00', 'done'), fb_id='1')
        with mock.patch.object(P, 'fb_post') as f, mock.patch.object(P, 'save'):
            P.fb_mirror([x], x)
        f.assert_not_called()

if __name__ == '__main__':
    unittest.main()

import math
import os
import threading
from collections import OrderedDict
from datetime import timedelta
from queue import Queue
from time import sleep

import pytest
import redis
import redis.client
from redis.exceptions import ResponseError

import fakeredis
import testtools
from testtools import raw_command


def key_val_dict(size=100):
    return {b'key:' + bytes([i]): b'val:' + bytes([i])
            for i in range(size)}


def round_str(x):
    assert isinstance(x, bytes)
    return round(float(x))


def zincrby(r, key, amount, value):
    return r.zincrby(key, amount, value)


def test_large_command(r):
    r.set('foo', 'bar' * 10000)
    assert r.get('foo') == b'bar' * 10000


def test_saving_non_ascii_chars_as_value(r):
    assert r.set('foo', 'Ñandu') is True
    assert r.get('foo') == 'Ñandu'.encode()


def test_saving_unicode_type_as_value(r):
    assert r.set('foo', 'Ñandu') is True
    assert r.get('foo') == 'Ñandu'.encode()


def test_saving_non_ascii_chars_as_key(r):
    assert r.set('Ñandu', 'foo') is True
    assert r.get('Ñandu') == b'foo'


def test_saving_unicode_type_as_key(r):
    assert r.set('Ñandu', 'foo') is True
    assert r.get('Ñandu') == b'foo'


def test_future_newbytes(r):
    # bytes = pytest.importorskip('builtins', reason='future.types not available').bytes
    r.set(bytes(b'\xc3\x91andu'), 'foo')
    assert r.get('Ñandu') == b'foo'


def test_future_newstr(r):
    # str = pytest.importorskip('builtins', reason='future.types not available').str
    r.set(str('Ñandu'), 'foo')
    assert r.get('Ñandu') == b'foo'


def test_get_does_not_exist(r):
    assert r.get('foo') is None


def test_get_with_non_str_keys(r):
    assert r.set('2', 'bar') is True
    assert r.get(2) == b'bar'


def test_get_invalid_type(r):
    assert r.hset('foo', 'key', 'value') == 1
    with pytest.raises(redis.ResponseError):
        r.get('foo')


def test_set_non_str_keys(r):
    assert r.set(2, 'bar') is True
    assert r.get(2) == b'bar'
    assert r.get('2') == b'bar'


def test_getbit(r):
    r.setbit('foo', 3, 1)
    assert r.getbit('foo', 0) == 0
    assert r.getbit('foo', 1) == 0
    assert r.getbit('foo', 2) == 0
    assert r.getbit('foo', 3) == 1
    assert r.getbit('foo', 4) == 0
    assert r.getbit('foo', 100) == 0


def test_getbit_wrong_type(r):
    r.rpush('foo', b'x')
    with pytest.raises(redis.ResponseError):
        r.getbit('foo', 1)


def test_multiple_bits_set(r):
    r.setbit('foo', 1, 1)
    r.setbit('foo', 3, 1)
    r.setbit('foo', 5, 1)

    assert r.getbit('foo', 0) == 0
    assert r.getbit('foo', 1) == 1
    assert r.getbit('foo', 2) == 0
    assert r.getbit('foo', 3) == 1
    assert r.getbit('foo', 4) == 0
    assert r.getbit('foo', 5) == 1
    assert r.getbit('foo', 6) == 0


def test_unset_bits(r):
    r.setbit('foo', 1, 1)
    r.setbit('foo', 2, 0)
    r.setbit('foo', 3, 1)
    assert r.getbit('foo', 1) == 1
    r.setbit('foo', 1, 0)
    assert r.getbit('foo', 1) == 0
    r.setbit('foo', 3, 0)
    assert r.getbit('foo', 3) == 0


def test_get_set_bits(r):
    # set bit 5
    assert not r.setbit('a', 5, True)
    assert r.getbit('a', 5)
    # unset bit 4
    assert not r.setbit('a', 4, False)
    assert not r.getbit('a', 4)
    # set bit 4
    assert not r.setbit('a', 4, True)
    assert r.getbit('a', 4)
    # set bit 5 again
    assert r.setbit('a', 5, True)
    assert r.getbit('a', 5)


def test_setbits_and_getkeys(r):
    # The bit operations and the get commands
    # should play nicely with each other.
    r.setbit('foo', 1, 1)
    assert r.get('foo') == b'@'
    r.setbit('foo', 2, 1)
    assert r.get('foo') == b'`'
    r.setbit('foo', 3, 1)
    assert r.get('foo') == b'p'
    r.setbit('foo', 9, 1)
    assert r.get('foo') == b'p@'
    r.setbit('foo', 54, 1)
    assert r.get('foo') == b'p@\x00\x00\x00\x00\x02'


def test_setbit_wrong_type(r):
    r.rpush('foo', b'x')
    with pytest.raises(redis.ResponseError):
        r.setbit('foo', 0, 1)


def test_setbit_expiry(r):
    r.set('foo', b'0x00', ex=10)
    r.setbit('foo', 1, 1)
    assert r.ttl('foo') > 0


def test_bitcount(r):
    r.delete('foo')
    assert r.bitcount('foo') == 0
    r.setbit('foo', 1, 1)
    assert r.bitcount('foo') == 1
    r.setbit('foo', 8, 1)
    assert r.bitcount('foo') == 2
    assert r.bitcount('foo', 1, 1) == 1
    r.setbit('foo', 57, 1)
    assert r.bitcount('foo') == 3
    r.set('foo', ' ')
    assert r.bitcount('foo') == 1


def test_bitcount_wrong_type(r):
    r.rpush('foo', b'x')
    with pytest.raises(redis.ResponseError):
        r.bitcount('foo')


def test_getset_not_exist(r):
    val = r.getset('foo', 'bar')
    assert val is None
    assert r.get('foo') == b'bar'


def test_getset_exists(r):
    r.set('foo', 'bar')
    val = r.getset('foo', b'baz')
    assert val == b'bar'
    val = r.getset('foo', b'baz2')
    assert val == b'baz'


def test_getset_wrong_type(r):
    r.rpush('foo', b'x')
    with pytest.raises(redis.ResponseError):
        r.getset('foo', 'bar')


def test_setitem_getitem(r):
    assert r.keys() == []
    r['foo'] = 'bar'
    assert r['foo'] == b'bar'


def test_getitem_non_existent_key(r):
    assert r.keys() == []
    assert 'noexists' not in r.keys()


def test_strlen(r):
    r['foo'] = 'bar'

    assert r.strlen('foo') == 3
    assert r.strlen('noexists') == 0


def test_strlen_wrong_type(r):
    r.rpush('foo', b'x')
    with pytest.raises(redis.ResponseError):
        r.strlen('foo')


def test_substr(r):
    r['foo'] = 'one_two_three'
    assert r.substr('foo', 0) == b'one_two_three'
    assert r.substr('foo', 0, 2) == b'one'
    assert r.substr('foo', 4, 6) == b'two'
    assert r.substr('foo', -5) == b'three'
    assert r.substr('foo', -4, -5) == b''
    assert r.substr('foo', -5, -3) == b'thr'


def test_substr_noexist_key(r):
    assert r.substr('foo', 0) == b''
    assert r.substr('foo', 10) == b''
    assert r.substr('foo', -5, -1) == b''


def test_substr_wrong_type(r):
    r.rpush('foo', b'x')
    with pytest.raises(redis.ResponseError):
        r.substr('foo', 0)


def test_append(r):
    assert r.set('foo', 'bar')
    assert r.append('foo', 'baz') == 6
    assert r.get('foo') == b'barbaz'


def test_append_with_no_preexisting_key(r):
    assert r.append('foo', 'bar') == 3
    assert r.get('foo') == b'bar'


def test_append_wrong_type(r):
    r.rpush('foo', b'x')
    with pytest.raises(redis.ResponseError):
        r.append('foo', b'x')


def test_incr_with_no_preexisting_key(r):
    assert r.incr('foo') == 1
    assert r.incr('bar', 2) == 2


def test_incr_by(r):
    assert r.incrby('foo') == 1
    assert r.incrby('bar', 2) == 2


def test_incr_preexisting_key(r):
    r.set('foo', 15)
    assert r.incr('foo', 5) == 20
    assert r.get('foo') == b'20'


def test_incr_expiry(r):
    r.set('foo', 15, ex=10)
    r.incr('foo', 5)
    assert r.ttl('foo') > 0


def test_incr_bad_type(r):
    r.set('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.incr('foo', 15)
    r.rpush('foo2', 1)
    with pytest.raises(redis.ResponseError):
        r.incr('foo2', 15)


def test_incr_with_float(r):
    with pytest.raises(redis.ResponseError):
        r.incr('foo', 2.0)


def test_incr_followed_by_mget(r):
    r.set('foo', 15)
    assert r.incr('foo', 5) == 20
    assert r.get('foo') == b'20'


def test_incr_followed_by_mget_returns_strings(r):
    r.incr('foo', 1)
    assert r.mget(['foo']) == [b'1']


def test_incrbyfloat(r):
    r.set('foo', 0)
    assert r.incrbyfloat('foo', 1.0) == 1.0
    assert r.incrbyfloat('foo', 1.0) == 2.0


def test_incrbyfloat_with_noexist(r):
    assert r.incrbyfloat('foo', 1.0) == 1.0
    assert r.incrbyfloat('foo', 1.0) == 2.0


def test_incrbyfloat_expiry(r):
    r.set('foo', 1.5, ex=10)
    r.incrbyfloat('foo', 2.5)
    assert r.ttl('foo') > 0


def test_incrbyfloat_bad_type(r):
    r.set('foo', 'bar')
    with pytest.raises(redis.ResponseError, match='not a valid float'):
        r.incrbyfloat('foo', 1.0)
    r.rpush('foo2', 1)
    with pytest.raises(redis.ResponseError):
        r.incrbyfloat('foo2', 1.0)


def test_incrbyfloat_precision(r):
    x = 1.23456789123456789
    assert r.incrbyfloat('foo', x) == x
    assert float(r.get('foo')) == x


def test_decr(r):
    r.set('foo', 10)
    assert r.decr('foo') == 9
    assert r.get('foo') == b'9'


def test_decr_newkey(r):
    r.decr('foo')
    assert r.get('foo') == b'-1'


def test_decr_expiry(r):
    r.set('foo', 10, ex=10)
    r.decr('foo', 5)
    assert r.ttl('foo') > 0


def test_decr_badtype(r):
    r.set('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.decr('foo', 15)
    r.rpush('foo2', 1)
    with pytest.raises(redis.ResponseError):
        r.decr('foo2', 15)


def test_keys(r):
    r.set('', 'empty')
    r.set('abc\n', '')
    r.set('abc\\', '')
    r.set('abcde', '')
    r.set(b'\xfe\xcd', '')
    assert sorted(r.keys()) == [b'', b'abc\n', b'abc\\', b'abcde', b'\xfe\xcd']
    assert r.keys('??') == [b'\xfe\xcd']
    # empty pattern not the same as no pattern
    assert r.keys('') == [b'']
    # ? must match \n
    assert sorted(r.keys('abc?')) == [b'abc\n', b'abc\\']
    # must be anchored at both ends
    assert r.keys('abc') == []
    assert r.keys('bcd') == []
    # wildcard test
    assert r.keys('a*de') == [b'abcde']
    # positive groups
    assert sorted(r.keys('abc[d\n]*')) == [b'abc\n', b'abcde']
    assert r.keys('abc[c-e]?') == [b'abcde']
    assert r.keys('abc[e-c]?') == [b'abcde']
    assert r.keys('abc[e-e]?') == []
    assert r.keys('abcd[ef') == [b'abcde']
    assert r.keys('abcd[]') == []
    # negative groups
    assert r.keys('abc[^d\\\\]*') == [b'abc\n']
    assert r.keys('abc[^]e') == [b'abcde']
    # escaping
    assert r.keys(r'abc\?e') == []
    assert r.keys(r'abc\de') == [b'abcde']
    assert r.keys(r'abc[\d]e') == [b'abcde']
    # some escaping cases that redis handles strangely
    assert r.keys('abc\\') == [b'abc\\']
    assert r.keys(r'abc[\c-e]e') == []
    assert r.keys(r'abc[c-\e]e') == []


def test_contains(r):
    assert not r.exists('foo')
    r.set('foo', 'bar')
    assert r.exists('foo')


def test_rename(r):
    r.set('foo', 'unique value')
    assert r.rename('foo', 'bar')
    assert r.get('foo') is None
    assert r.get('bar') == b'unique value'


def test_rename_nonexistent_key(r):
    with pytest.raises(redis.ResponseError):
        r.rename('foo', 'bar')


def test_renamenx_doesnt_exist(r):
    r.set('foo', 'unique value')
    assert r.renamenx('foo', 'bar')
    assert r.get('foo') is None
    assert r.get('bar') == b'unique value'


def test_rename_does_exist(r):
    r.set('foo', 'unique value')
    r.set('bar', 'unique value2')
    assert not r.renamenx('foo', 'bar')
    assert r.get('foo') == b'unique value'
    assert r.get('bar') == b'unique value2'


def test_rename_expiry(r):
    r.set('foo', 'value1', ex=10)
    r.set('bar', 'value2')
    r.rename('foo', 'bar')
    assert r.ttl('bar') > 0


def test_mget(r):
    r.set('foo', 'one')
    r.set('bar', 'two')
    assert r.mget(['foo', 'bar']) == [b'one', b'two']
    assert r.mget(['foo', 'bar', 'baz']) == [b'one', b'two', None]
    assert r.mget('foo', 'bar') == [b'one', b'two']


def test_mget_with_no_keys(r):
    assert r.mget([]) == []


def test_mget_mixed_types(r):
    r.hset('hash', 'bar', 'baz')
    testtools.zadd(r, 'zset', {'bar': 1})
    r.sadd('set', 'member')
    r.rpush('list', 'item1')
    r.set('string', 'value')
    assert (
            r.mget(['hash', 'zset', 'set', 'string', 'absent'])
            == [None, None, None, b'value', None]
    )


def test_mset_with_no_keys(r):
    with pytest.raises(redis.ResponseError):
        r.mset({})


def test_mset(r):
    assert r.mset({'foo': 'one', 'bar': 'two'}) is True
    assert r.mset({'foo': 'one', 'bar': 'two'}) is True
    assert r.mget('foo', 'bar') == [b'one', b'two']


def test_msetnx(r):
    assert r.msetnx({'foo': 'one', 'bar': 'two'}) is True
    assert r.msetnx({'bar': 'two', 'baz': 'three'}) is False
    assert r.mget('foo', 'bar', 'baz') == [b'one', b'two', None]


def test_setex(r):
    assert r.setex('foo', 100, 'bar') is True
    assert r.get('foo') == b'bar'


def test_setex_using_timedelta(r):
    assert r.setex('foo', timedelta(seconds=100), 'bar') is True
    assert r.get('foo') == b'bar'


def test_setex_using_float(r):
    with pytest.raises(redis.ResponseError, match='integer'):
        r.setex('foo', 1.2, 'bar')


@pytest.mark.min_server('6.2')
def test_setex_overflow(r):
    with pytest.raises(ResponseError):
        r.setex('foo', 18446744073709561, 'bar')  # Overflows long long in ms


def test_set_ex(r):
    assert r.set('foo', 'bar', ex=100) is True
    assert r.get('foo') == b'bar'


def test_set_ex_using_timedelta(r):
    assert r.set('foo', 'bar', ex=timedelta(seconds=100)) is True
    assert r.get('foo') == b'bar'


def test_set_ex_overflow(r):
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', ex=18446744073709561)  # Overflows long long in ms


def test_set_px_overflow(r):
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', px=2 ** 63 - 2)  # Overflows after adding current time


def test_set_px(r):
    assert r.set('foo', 'bar', px=100) is True
    assert r.get('foo') == b'bar'


def test_set_px_using_timedelta(r):
    assert r.set('foo', 'bar', px=timedelta(milliseconds=100)) is True
    assert r.get('foo') == b'bar'


@testtools.run_test_if_redispy_ver('below', '3.5')
@pytest.mark.min_server('6.0')
def test_set_keepttl(r):
    r.set('foo', 'bar', ex=100)
    assert r.set('foo', 'baz', keepttl=True) is True
    assert r.ttl('foo') == 100
    assert r.get('foo') == b'baz'


def test_set_conflicting_expire_options(r):
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', ex=1, px=1)


@testtools.run_test_if_redispy_ver('below', '3.5')
def test_set_conflicting_expire_options_w_keepttl(r):
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', ex=1, keepttl=True)
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', px=1, keepttl=True)
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', ex=1, px=1, keepttl=True)


def test_set_raises_wrong_ex(r):
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', ex=-100)
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', ex=0)
    assert not r.exists('foo')


def test_set_using_timedelta_raises_wrong_ex(r):
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', ex=timedelta(seconds=-100))
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', ex=timedelta(seconds=0))
    assert not r.exists('foo')


def test_set_raises_wrong_px(r):
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', px=-100)
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', px=0)
    assert not r.exists('foo')


def test_set_using_timedelta_raises_wrong_px(r):
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', px=timedelta(milliseconds=-100))
    with pytest.raises(ResponseError):
        r.set('foo', 'bar', px=timedelta(milliseconds=0))
    assert not r.exists('foo')


def test_setex_raises_wrong_ex(r):
    with pytest.raises(ResponseError):
        r.setex('foo', -100, 'bar')
    with pytest.raises(ResponseError):
        r.setex('foo', 0, 'bar')
    assert not r.exists('foo')


def test_setex_using_timedelta_raises_wrong_ex(r):
    with pytest.raises(ResponseError):
        r.setex('foo', timedelta(seconds=-100), 'bar')
    with pytest.raises(ResponseError):
        r.setex('foo', timedelta(seconds=-100), 'bar')
    assert not r.exists('foo')


def test_setnx(r):
    assert r.setnx('foo', 'bar') is True
    assert r.get('foo') == b'bar'
    assert r.setnx('foo', 'baz') is False
    assert r.get('foo') == b'bar'


def test_set_nx(r):
    assert r.set('foo', 'bar', nx=True) is True
    assert r.get('foo') == b'bar'
    assert r.set('foo', 'bar', nx=True) is None
    assert r.get('foo') == b'bar'


def test_set_xx(r):
    assert r.set('foo', 'bar', xx=True) is None
    r.set('foo', 'bar')
    assert r.set('foo', 'bar', xx=True) is True


@pytest.mark.min_server('6.2')
def test_set_get(r):
    assert raw_command(r, 'set', 'foo', 'bar', 'GET') is None
    assert r.get('foo') == b'bar'
    assert raw_command(r, 'set', 'foo', 'baz', 'GET') == b'bar'
    assert r.get('foo') == b'baz'


@pytest.mark.min_server('6.2')
def test_set_get_xx(r):
    assert raw_command(r, 'set', 'foo', 'bar', 'XX', 'GET') is None
    assert r.get('foo') is None
    r.set('foo', 'bar')
    assert raw_command(r, 'set', 'foo', 'baz', 'XX', 'GET') == b'bar'
    assert r.get('foo') == b'baz'
    assert raw_command(r, 'set', 'foo', 'baz', 'GET') == b'baz'


@pytest.mark.min_server('6.2')
@pytest.mark.max_server('6.2.7')
def test_set_get_nx(r):
    # Note: this will most likely fail on a 7.0 server, based on the docs for SET
    with pytest.raises(redis.ResponseError):
        raw_command(r, 'set', 'foo', 'bar', 'NX', 'GET')


@pytest.mark.min_server('6.2')
def set_get_wrongtype(r):
    r.lpush('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        raw_command(r, 'set', 'foo', 'bar', 'GET')


def test_delete(r):
    r['foo'] = 'bar'
    assert r.delete('foo') == 1
    assert r.get('foo') is None


@testtools.run_test_if_redispy_ver('above', '4.0.0')
def test_getdel(r):
    r['foo'] = 'bar'
    assert r.getdel('foo') == b'bar'
    assert r.get('foo') is None


@testtools.run_test_if_redispy_ver('above', '4.0.0')
def test_getdel_doesnt_exist(r):
    assert r.getdel('foo') is None


def test_echo(r):
    assert r.echo(b'hello') == b'hello'
    assert r.echo('hello') == b'hello'


@pytest.mark.slow
def test_delete_expire(r):
    r.set("foo", "bar", ex=1)
    r.delete("foo")
    r.set("foo", "bar")
    sleep(2)
    assert r.get("foo") == b'bar'


def test_delete_multiple(r):
    r['one'] = 'one'
    r['two'] = 'two'
    r['three'] = 'three'
    # Since redis>=2.7.6 returns number of deleted items.
    assert r.delete('one', 'two') == 2
    assert r.get('one') is None
    assert r.get('two') is None
    assert r.get('three') == b'three'
    assert r.delete('one', 'two') == 0
    # If any keys are deleted, True is returned.
    assert r.delete('two', 'three', 'three') == 1
    assert r.get('three') is None


def test_delete_nonexistent_key(r):
    assert r.delete('foo') == 0


def test_sadd(r):
    assert r.sadd('foo', 'member1') == 1
    assert r.sadd('foo', 'member1') == 0
    assert r.smembers('foo') == {b'member1'}
    assert r.sadd('foo', 'member2', 'member3') == 2
    assert r.smembers('foo') == {b'member1', b'member2', b'member3'}
    assert r.sadd('foo', 'member3', 'member4') == 1
    assert r.smembers('foo') == {b'member1', b'member2', b'member3', b'member4'}


def test_sadd_as_str_type(r):
    assert r.sadd('foo', *range(3)) == 3
    assert r.smembers('foo') == {b'0', b'1', b'2'}


def test_sadd_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    with pytest.raises(redis.ResponseError):
        r.sadd('foo', 'member2')


def test_scan_single(r):
    r.set('foo1', 'bar1')
    assert r.scan(match="foo*") == (0, [b'foo1'])


def test_scan_iter_single_page(r):
    r.set('foo1', 'bar1')
    r.set('foo2', 'bar2')
    assert set(r.scan_iter(match="foo*")) == {b'foo1', b'foo2'}
    assert set(r.scan_iter()) == {b'foo1', b'foo2'}
    assert set(r.scan_iter(match="")) == set()


def test_scan_iter_multiple_pages(r):
    all_keys = key_val_dict(size=100)
    assert all(r.set(k, v) for k, v in all_keys.items())
    assert set(r.scan_iter()) == set(all_keys)


def test_scan_iter_multiple_pages_with_match(r):
    all_keys = key_val_dict(size=100)
    assert all(r.set(k, v) for k, v in all_keys.items())
    # Now add a few keys that don't match the key:<number> pattern.
    r.set('otherkey', 'foo')
    r.set('andanother', 'bar')
    actual = set(r.scan_iter(match='key:*'))
    assert actual == set(all_keys)


@testtools.run_test_if_redispy_ver('below', '3.5')
@pytest.mark.min_server('6.0')
def test_scan_iter_multiple_pages_with_type(r):
    all_keys = key_val_dict(size=100)
    assert all(r.set(k, v) for k, v in all_keys.items())
    # Now add a few keys of another type
    testtools.zadd(r, 'zset1', {'otherkey': 1})
    testtools.zadd(r, 'zset2', {'andanother': 1})
    actual = set(r.scan_iter(_type='string'))
    assert actual == set(all_keys)
    actual = set(r.scan_iter(_type='ZSET'))
    assert actual == {b'zset1', b'zset2'}


def test_scan_multiple_pages_with_count_arg(r):
    all_keys = key_val_dict(size=100)
    assert all(r.set(k, v) for k, v in all_keys.items())
    assert set(r.scan_iter(count=1000)) == set(all_keys)


def test_scan_all_in_single_call(r):
    all_keys = key_val_dict(size=100)
    assert all(r.set(k, v) for k, v in all_keys.items())
    # Specify way more than the 100 keys we've added.
    actual = r.scan(count=1000)
    assert set(actual[1]) == set(all_keys)
    assert actual[0] == 0


@pytest.mark.slow
def test_scan_expired_key(r):
    r.set('expiringkey', 'value')
    r.pexpire('expiringkey', 1)
    sleep(1)
    assert r.scan()[1] == []


def test_scard(r):
    r.sadd('foo', 'member1')
    r.sadd('foo', 'member2')
    r.sadd('foo', 'member2')
    assert r.scard('foo') == 2


def test_scard_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    with pytest.raises(redis.ResponseError):
        r.scard('foo')


def test_sdiff(r):
    r.sadd('foo', 'member1')
    r.sadd('foo', 'member2')
    r.sadd('bar', 'member2')
    r.sadd('bar', 'member3')
    assert r.sdiff('foo', 'bar') == {b'member1'}
    # Original sets shouldn't be modified.
    assert r.smembers('foo') == {b'member1', b'member2'}
    assert r.smembers('bar') == {b'member2', b'member3'}


def test_sdiff_one_key(r):
    r.sadd('foo', 'member1')
    r.sadd('foo', 'member2')
    assert r.sdiff('foo') == {b'member1', b'member2'}


def test_sdiff_empty(r):
    assert r.sdiff('foo') == set()


def test_sdiff_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    r.sadd('bar', 'member')
    with pytest.raises(redis.ResponseError):
        r.sdiff('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.sdiff('bar', 'foo')


def test_sdiffstore(r):
    r.sadd('foo', 'member1')
    r.sadd('foo', 'member2')
    r.sadd('bar', 'member2')
    r.sadd('bar', 'member3')
    assert r.sdiffstore('baz', 'foo', 'bar') == 1

    # Catch instances where we store bytes and strings inconsistently
    # and thus baz = {'member1', b'member1'}
    r.sadd('baz', 'member1')
    assert r.scard('baz') == 1


def test_setrange(r):
    r.set('foo', 'test')
    assert r.setrange('foo', 1, 'aste') == 5
    assert r.get('foo') == b'taste'

    r.set('foo', 'test')
    assert r.setrange('foo', 1, 'a') == 4
    assert r.get('foo') == b'tast'

    assert r.setrange('bar', 2, 'test') == 6
    assert r.get('bar') == b'\x00\x00test'


def test_setrange_expiry(r):
    r.set('foo', 'test', ex=10)
    r.setrange('foo', 1, 'aste')
    assert r.ttl('foo') > 0


def test_sinter(r):
    r.sadd('foo', 'member1')
    r.sadd('foo', 'member2')
    r.sadd('bar', 'member2')
    r.sadd('bar', 'member3')
    assert r.sinter('foo', 'bar') == {b'member2'}
    assert r.sinter('foo') == {b'member1', b'member2'}


def test_sinter_bytes_keys(r):
    foo = os.urandom(10)
    bar = os.urandom(10)
    r.sadd(foo, 'member1')
    r.sadd(foo, 'member2')
    r.sadd(bar, 'member2')
    r.sadd(bar, 'member3')
    assert r.sinter(foo, bar) == {b'member2'}
    assert r.sinter(foo) == {b'member1', b'member2'}


def test_sinter_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    r.sadd('bar', 'member')
    with pytest.raises(redis.ResponseError):
        r.sinter('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.sinter('bar', 'foo')


def test_sinterstore(r):
    r.sadd('foo', 'member1')
    r.sadd('foo', 'member2')
    r.sadd('bar', 'member2')
    r.sadd('bar', 'member3')
    assert r.sinterstore('baz', 'foo', 'bar') == 1

    # Catch instances where we store bytes and strings inconsistently
    # and thus baz = {'member2', b'member2'}
    r.sadd('baz', 'member2')
    assert r.scard('baz') == 1


def test_sismember(r):
    assert r.sismember('foo', 'member1') is False
    r.sadd('foo', 'member1')
    assert r.sismember('foo', 'member1') is True


def test_sismember_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    with pytest.raises(redis.ResponseError):
        r.sismember('foo', 'member')


def test_smembers(r):
    assert r.smembers('foo') == set()


def test_smembers_copy(r):
    r.sadd('foo', 'member1')
    ret = r.smembers('foo')
    r.sadd('foo', 'member2')
    assert r.smembers('foo') != ret


def test_smembers_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    with pytest.raises(redis.ResponseError):
        r.smembers('foo')


def test_smembers_runtime_error(r):
    r.sadd('foo', 'member1', 'member2')
    for member in r.smembers('foo'):
        r.srem('foo', member)


def test_smove(r):
    r.sadd('foo', 'member1')
    r.sadd('foo', 'member2')
    assert r.smove('foo', 'bar', 'member1') is True
    assert r.smembers('bar') == {b'member1'}


def test_smove_non_existent_key(r):
    assert r.smove('foo', 'bar', 'member1') is False


def test_smove_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    r.sadd('bar', 'member')
    with pytest.raises(redis.ResponseError):
        r.smove('bar', 'foo', 'member')
    # Must raise the error before removing member from bar
    assert r.smembers('bar') == {b'member'}
    with pytest.raises(redis.ResponseError):
        r.smove('foo', 'bar', 'member')


def test_spop(r):
    # This is tricky because it pops a random element.
    r.sadd('foo', 'member1')
    assert r.spop('foo') == b'member1'
    assert r.spop('foo') is None


def test_spop_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    with pytest.raises(redis.ResponseError):
        r.spop('foo')


def test_srandmember(r):
    r.sadd('foo', 'member1')
    assert r.srandmember('foo') == b'member1'
    # Shouldn't be removed from the set.
    assert r.srandmember('foo') == b'member1'


def test_srandmember_number(r):
    """srandmember works with the number argument."""
    assert r.srandmember('foo', 2) == []
    r.sadd('foo', b'member1')
    assert r.srandmember('foo', 2) == [b'member1']
    r.sadd('foo', b'member2')
    assert set(r.srandmember('foo', 2)) == {b'member1', b'member2'}
    r.sadd('foo', b'member3')
    res = r.srandmember('foo', 2)
    assert len(res) == 2
    for e in res:
        assert e in {b'member1', b'member2', b'member3'}


def test_srandmember_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    with pytest.raises(redis.ResponseError):
        r.srandmember('foo')


def test_srem(r):
    r.sadd('foo', 'member1', 'member2', 'member3', 'member4')
    assert r.smembers('foo') == {b'member1', b'member2', b'member3', b'member4'}
    assert r.srem('foo', 'member1') == 1
    assert r.smembers('foo') == {b'member2', b'member3', b'member4'}
    assert r.srem('foo', 'member1') == 0
    # Since redis>=2.7.6 returns number of deleted items.
    assert r.srem('foo', 'member2', 'member3') == 2
    assert r.smembers('foo') == {b'member4'}
    assert r.srem('foo', 'member3', 'member4') == 1
    assert r.smembers('foo') == set()
    assert r.srem('foo', 'member3', 'member4') == 0


def test_srem_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    with pytest.raises(redis.ResponseError):
        r.srem('foo', 'member')


def test_sunion(r):
    r.sadd('foo', 'member1')
    r.sadd('foo', 'member2')
    r.sadd('bar', 'member2')
    r.sadd('bar', 'member3')
    assert r.sunion('foo', 'bar') == {b'member1', b'member2', b'member3'}


def test_sunion_wrong_type(r):
    testtools.zadd(r, 'foo', {'member': 1})
    r.sadd('bar', 'member')
    with pytest.raises(redis.ResponseError):
        r.sunion('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.sunion('bar', 'foo')


def test_sunionstore(r):
    r.sadd('foo', 'member1')
    r.sadd('foo', 'member2')
    r.sadd('bar', 'member2')
    r.sadd('bar', 'member3')
    assert r.sunionstore('baz', 'foo', 'bar') == 3
    assert r.smembers('baz') == {b'member1', b'member2', b'member3'}

    # Catch instances where we store bytes and strings inconsistently
    # and thus baz = {b'member1', b'member2', b'member3', 'member3'}
    r.sadd('baz', 'member3')
    assert r.scard('baz') == 3


def test_empty_set(r):
    r.sadd('foo', 'bar')
    r.srem('foo', 'bar')
    assert not r.exists('foo')


def test_zrange_same_score(r):
    testtools.zadd(r, 'foo', {'two_a': 2})
    testtools.zadd(r, 'foo', {'two_b': 2})
    testtools.zadd(r, 'foo', {'two_c': 2})
    testtools.zadd(r, 'foo', {'two_d': 2})
    testtools.zadd(r, 'foo', {'two_e': 2})
    assert r.zrange('foo', 2, 3) == [b'two_c', b'two_d']


def test_zcard(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    assert r.zcard('foo') == 2


def test_zcard_non_existent_key(r):
    assert r.zcard('foo') == 0


def test_zcard_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zcard('foo')


def test_zcount(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'three': 2})
    testtools.zadd(r, 'foo', {'five': 5})
    assert r.zcount('foo', 2, 4) == 1
    assert r.zcount('foo', 1, 4) == 2
    assert r.zcount('foo', 0, 5) == 3
    assert r.zcount('foo', 4, '+inf') == 1
    assert r.zcount('foo', '-inf', 4) == 2
    assert r.zcount('foo', '-inf', '+inf') == 3


def test_zcount_exclusive(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'three': 2})
    testtools.zadd(r, 'foo', {'five': 5})
    assert r.zcount('foo', '-inf', '(2') == 1
    assert r.zcount('foo', '-inf', 2) == 2
    assert r.zcount('foo', '(5', '+inf') == 0
    assert r.zcount('foo', '(1', 5) == 2
    assert r.zcount('foo', '(2', '(5') == 0
    assert r.zcount('foo', '(1', '(5') == 1
    assert r.zcount('foo', 2, '(5') == 1


def test_zcount_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zcount('foo', '-inf', '+inf')


def test_zincrby(r):
    testtools.zadd(r, 'foo', {'one': 1})
    assert zincrby(r, 'foo', 10, 'one') == 11
    assert r.zrange('foo', 0, -1, withscores=True) == [(b'one', 11)]


def test_zincrby_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        zincrby(r, 'foo', 10, 'one')


def test_zrange_descending(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zrange('foo', 0, -1, desc=True) == [b'three', b'two', b'one']


def test_zrange_descending_with_scores(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert (
            r.zrange('foo', 0, -1, desc=True, withscores=True)
            == [(b'three', 3), (b'two', 2), (b'one', 1)]
    )


def test_zrange_with_positive_indices(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zrange('foo', 0, 1) == [b'one', b'two']


def test_zrange_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zrange('foo', 0, -1)


def test_zrange_score_cast(r):
    testtools.zadd(r, 'foo', {'one': 1.2})
    testtools.zadd(r, 'foo', {'two': 2.2})

    expected_without_cast_round = [(b'one', 1.2), (b'two', 2.2)]
    expected_with_cast_round = [(b'one', 1.0), (b'two', 2.0)]
    assert r.zrange('foo', 0, 2, withscores=True) == expected_without_cast_round
    assert (
            r.zrange('foo', 0, 2, withscores=True, score_cast_func=round_str)
            == expected_with_cast_round
    )


def test_zrank(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zrank('foo', 'one') == 0
    assert r.zrank('foo', 'two') == 1
    assert r.zrank('foo', 'three') == 2


def test_zrank_non_existent_member(r):
    assert r.zrank('foo', 'one') is None


def test_zrank_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zrank('foo', 'one')


def test_zrem(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    testtools.zadd(r, 'foo', {'four': 4})
    assert r.zrem('foo', 'one') == 1
    assert r.zrange('foo', 0, -1) == [b'two', b'three', b'four']
    # Since redis>=2.7.6 returns number of deleted items.
    assert r.zrem('foo', 'two', 'three') == 2
    assert r.zrange('foo', 0, -1) == [b'four']
    assert r.zrem('foo', 'three', 'four') == 1
    assert r.zrange('foo', 0, -1) == []
    assert r.zrem('foo', 'three', 'four') == 0


def test_zrem_non_existent_member(r):
    assert not r.zrem('foo', 'one')


def test_zrem_numeric_member(r):
    testtools.zadd(r, 'foo', {'128': 13.0, '129': 12.0})
    assert r.zrem('foo', 128) == 1
    assert r.zrange('foo', 0, -1) == [b'129']


def test_zrem_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zrem('foo', 'bar')


def test_zscore(r):
    testtools.zadd(r, 'foo', {'one': 54})
    assert r.zscore('foo', 'one') == 54


def test_zscore_non_existent_member(r):
    assert r.zscore('foo', 'one') is None


def test_zscore_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zscore('foo', 'one')


def test_zrevrank(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zrevrank('foo', 'one') == 2
    assert r.zrevrank('foo', 'two') == 1
    assert r.zrevrank('foo', 'three') == 0


def test_zrevrank_non_existent_member(r):
    assert r.zrevrank('foo', 'one') is None


def test_zrevrank_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zrevrank('foo', 'one')


def test_zrevrange(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zrevrange('foo', 0, 1) == [b'three', b'two']
    assert r.zrevrange('foo', 0, -1) == [b'three', b'two', b'one']


def test_zrevrange_sorted_keys(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'two_b': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zrevrange('foo', 0, 2) == [b'three', b'two_b', b'two']
    assert r.zrevrange('foo', 0, -1) == [b'three', b'two_b', b'two', b'one']


def test_zrevrange_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zrevrange('foo', 0, 2)


def test_zrevrange_score_cast(r):
    testtools.zadd(r, 'foo', {'one': 1.2})
    testtools.zadd(r, 'foo', {'two': 2.2})

    expected_without_cast_round = [(b'two', 2.2), (b'one', 1.2)]
    expected_with_cast_round = [(b'two', 2.0), (b'one', 1.0)]
    assert r.zrevrange('foo', 0, 2, withscores=True) == expected_without_cast_round
    assert (
            r.zrevrange('foo', 0, 2, withscores=True, score_cast_func=round_str)
            == expected_with_cast_round
    )


def test_zrange_with_large_int(r):
    with pytest.raises(redis.ResponseError, match='value is not an integer or out of range'):
        r.zrange('', 0, 9223372036854775808)
    with pytest.raises(redis.ResponseError, match='value is not an integer or out of range'):
        r.zrange('', 0, -9223372036854775809)


def test_zrangebyscore(r):
    testtools.zadd(r, 'foo', {'zero': 0})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'two_a_also': 2})
    testtools.zadd(r, 'foo', {'two_b_also': 2})
    testtools.zadd(r, 'foo', {'four': 4})
    assert r.zrangebyscore('foo', 1, 3) == [b'two', b'two_a_also', b'two_b_also']
    assert r.zrangebyscore('foo', 2, 3) == [b'two', b'two_a_also', b'two_b_also']
    assert (
            r.zrangebyscore('foo', 0, 4)
            == [b'zero', b'two', b'two_a_also', b'two_b_also', b'four']
    )
    assert r.zrangebyscore('foo', '-inf', 1) == [b'zero']
    assert (
            r.zrangebyscore('foo', 2, '+inf')
            == [b'two', b'two_a_also', b'two_b_also', b'four']
    )
    assert (
            r.zrangebyscore('foo', '-inf', '+inf')
            == [b'zero', b'two', b'two_a_also', b'two_b_also', b'four']
    )


def test_zrangebysore_exclusive(r):
    testtools.zadd(r, 'foo', {'zero': 0})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'four': 4})
    testtools.zadd(r, 'foo', {'five': 5})
    assert r.zrangebyscore('foo', '(0', 6) == [b'two', b'four', b'five']
    assert r.zrangebyscore('foo', '(2', '(5') == [b'four']
    assert r.zrangebyscore('foo', 0, '(4') == [b'zero', b'two']


def test_zrangebyscore_raises_error(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    with pytest.raises(redis.ResponseError):
        r.zrangebyscore('foo', 'one', 2)
    with pytest.raises(redis.ResponseError):
        r.zrangebyscore('foo', 2, 'three')
    with pytest.raises(redis.ResponseError):
        r.zrangebyscore('foo', 2, '3)')
    with pytest.raises(redis.RedisError):
        r.zrangebyscore('foo', 2, '3)', 0, None)


def test_zrangebyscore_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zrangebyscore('foo', '(1', '(2')


def test_zrangebyscore_slice(r):
    testtools.zadd(r, 'foo', {'two_a': 2})
    testtools.zadd(r, 'foo', {'two_b': 2})
    testtools.zadd(r, 'foo', {'two_c': 2})
    testtools.zadd(r, 'foo', {'two_d': 2})
    assert r.zrangebyscore('foo', 0, 4, 0, 2) == [b'two_a', b'two_b']
    assert r.zrangebyscore('foo', 0, 4, 1, 3) == [b'two_b', b'two_c', b'two_d']


def test_zrangebyscore_withscores(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zrangebyscore('foo', 1, 3, 0, 2, True) == [(b'one', 1), (b'two', 2)]


def test_zrangebyscore_cast_scores(r):
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'two_a_also': 2.2})

    expected_without_cast_round = [(b'two', 2.0), (b'two_a_also', 2.2)]
    expected_with_cast_round = [(b'two', 2.0), (b'two_a_also', 2.0)]
    assert (
            sorted(r.zrangebyscore('foo', 2, 3, withscores=True))
            == sorted(expected_without_cast_round)
    )
    assert (
            sorted(r.zrangebyscore('foo', 2, 3, withscores=True,
                                   score_cast_func=round_str))
            == sorted(expected_with_cast_round)
    )


def test_zrevrangebyscore(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zrevrangebyscore('foo', 3, 1) == [b'three', b'two', b'one']
    assert r.zrevrangebyscore('foo', 3, 2) == [b'three', b'two']
    assert r.zrevrangebyscore('foo', 3, 1, 0, 1) == [b'three']
    assert r.zrevrangebyscore('foo', 3, 1, 1, 2) == [b'two', b'one']


def test_zrevrangebyscore_exclusive(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zrevrangebyscore('foo', '(3', 1) == [b'two', b'one']
    assert r.zrevrangebyscore('foo', 3, '(2') == [b'three']
    assert r.zrevrangebyscore('foo', '(3', '(1') == [b'two']
    assert r.zrevrangebyscore('foo', '(2', 1, 0, 1) == [b'one']
    assert r.zrevrangebyscore('foo', '(2', '(1', 0, 1) == []
    assert r.zrevrangebyscore('foo', '(3', '(0', 1, 2) == [b'one']


def test_zrevrangebyscore_raises_error(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    with pytest.raises(redis.ResponseError):
        r.zrevrangebyscore('foo', 'three', 1)
    with pytest.raises(redis.ResponseError):
        r.zrevrangebyscore('foo', 3, 'one')
    with pytest.raises(redis.ResponseError):
        r.zrevrangebyscore('foo', 3, '1)')
    with pytest.raises(redis.ResponseError):
        r.zrevrangebyscore('foo', '((3', '1)')


def test_zrevrangebyscore_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zrevrangebyscore('foo', '(3', '(1')


def test_zrevrangebyscore_cast_scores(r):
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'two_a_also': 2.2})

    expected_without_cast_round = [(b'two_a_also', 2.2), (b'two', 2.0)]
    expected_with_cast_round = [(b'two_a_also', 2.0), (b'two', 2.0)]
    assert (
            r.zrevrangebyscore('foo', 3, 2, withscores=True)
            == expected_without_cast_round
    )
    assert (
            r.zrevrangebyscore('foo', 3, 2, withscores=True,
                               score_cast_func=round_str)
            == expected_with_cast_round
    )


def test_zrangebylex(r):
    testtools.zadd(r, 'foo', {'one_a': 0})
    testtools.zadd(r, 'foo', {'two_a': 0})
    testtools.zadd(r, 'foo', {'two_b': 0})
    testtools.zadd(r, 'foo', {'three_a': 0})
    assert r.zrangebylex('foo', b'(t', b'+') == [b'three_a', b'two_a', b'two_b']
    assert r.zrangebylex('foo', b'(t', b'[two_b') == [b'three_a', b'two_a', b'two_b']
    assert r.zrangebylex('foo', b'(t', b'(two_b') == [b'three_a', b'two_a']
    assert (
            r.zrangebylex('foo', b'[three_a', b'[two_b')
            == [b'three_a', b'two_a', b'two_b']
    )
    assert r.zrangebylex('foo', b'(three_a', b'[two_b') == [b'two_a', b'two_b']
    assert r.zrangebylex('foo', b'-', b'(two_b') == [b'one_a', b'three_a', b'two_a']
    assert r.zrangebylex('foo', b'[two_b', b'(two_b') == []
    # reversed max + and min - boundaries
    # these will be always empty, but allowed by redis
    assert r.zrangebylex('foo', b'+', b'-') == []
    assert r.zrangebylex('foo', b'+', b'[three_a') == []
    assert r.zrangebylex('foo', b'[o', b'-') == []


def test_zrangebylex_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zrangebylex('foo', b'-', b'+')


def test_zlexcount(r):
    testtools.zadd(r, 'foo', {'one_a': 0})
    testtools.zadd(r, 'foo', {'two_a': 0})
    testtools.zadd(r, 'foo', {'two_b': 0})
    testtools.zadd(r, 'foo', {'three_a': 0})
    assert r.zlexcount('foo', b'(t', b'+') == 3
    assert r.zlexcount('foo', b'(t', b'[two_b') == 3
    assert r.zlexcount('foo', b'(t', b'(two_b') == 2
    assert r.zlexcount('foo', b'[three_a', b'[two_b') == 3
    assert r.zlexcount('foo', b'(three_a', b'[two_b') == 2
    assert r.zlexcount('foo', b'-', b'(two_b') == 3
    assert r.zlexcount('foo', b'[two_b', b'(two_b') == 0
    # reversed max + and min - boundaries
    # these will be always empty, but allowed by redis
    assert r.zlexcount('foo', b'+', b'-') == 0
    assert r.zlexcount('foo', b'+', b'[three_a') == 0
    assert r.zlexcount('foo', b'[o', b'-') == 0


def test_zlexcount_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zlexcount('foo', b'-', b'+')


def test_zrangebylex_with_limit(r):
    testtools.zadd(r, 'foo', {'one_a': 0})
    testtools.zadd(r, 'foo', {'two_a': 0})
    testtools.zadd(r, 'foo', {'two_b': 0})
    testtools.zadd(r, 'foo', {'three_a': 0})
    assert r.zrangebylex('foo', b'-', b'+', 1, 2) == [b'three_a', b'two_a']

    # negative offset no results
    assert r.zrangebylex('foo', b'-', b'+', -1, 3) == []

    # negative limit ignored
    assert (
            r.zrangebylex('foo', b'-', b'+', 0, -2)
            == [b'one_a', b'three_a', b'two_a', b'two_b']
    )
    assert r.zrangebylex('foo', b'-', b'+', 1, -2) == [b'three_a', b'two_a', b'two_b']
    assert r.zrangebylex('foo', b'+', b'-', 1, 1) == []


def test_zrangebylex_raises_error(r):
    testtools.zadd(r, 'foo', {'one_a': 0})
    testtools.zadd(r, 'foo', {'two_a': 0})
    testtools.zadd(r, 'foo', {'two_b': 0})
    testtools.zadd(r, 'foo', {'three_a': 0})

    with pytest.raises(redis.ResponseError):
        r.zrangebylex('foo', b'', b'[two_b')

    with pytest.raises(redis.ResponseError):
        r.zrangebylex('foo', b'-', b'two_b')

    with pytest.raises(redis.ResponseError):
        r.zrangebylex('foo', b'(t', b'two_b')

    with pytest.raises(redis.ResponseError):
        r.zrangebylex('foo', b't', b'+')

    with pytest.raises(redis.ResponseError):
        r.zrangebylex('foo', b'[two_a', b'')

    with pytest.raises(redis.RedisError):
        r.zrangebylex('foo', b'(two_a', b'[two_b', 1)


def test_zrevrangebylex(r):
    testtools.zadd(r, 'foo', {'one_a': 0})
    testtools.zadd(r, 'foo', {'two_a': 0})
    testtools.zadd(r, 'foo', {'two_b': 0})
    testtools.zadd(r, 'foo', {'three_a': 0})
    assert r.zrevrangebylex('foo', b'+', b'(t') == [b'two_b', b'two_a', b'three_a']
    assert (
            r.zrevrangebylex('foo', b'[two_b', b'(t')
            == [b'two_b', b'two_a', b'three_a']
    )
    assert r.zrevrangebylex('foo', b'(two_b', b'(t') == [b'two_a', b'three_a']
    assert (
            r.zrevrangebylex('foo', b'[two_b', b'[three_a')
            == [b'two_b', b'two_a', b'three_a']
    )
    assert r.zrevrangebylex('foo', b'[two_b', b'(three_a') == [b'two_b', b'two_a']
    assert r.zrevrangebylex('foo', b'(two_b', b'-') == [b'two_a', b'three_a', b'one_a']
    assert r.zrangebylex('foo', b'(two_b', b'[two_b') == []
    # reversed max + and min - boundaries
    # these will be always empty, but allowed by redis
    assert r.zrevrangebylex('foo', b'-', b'+') == []
    assert r.zrevrangebylex('foo', b'[three_a', b'+') == []
    assert r.zrevrangebylex('foo', b'-', b'[o') == []


def test_zrevrangebylex_with_limit(r):
    testtools.zadd(r, 'foo', {'one_a': 0})
    testtools.zadd(r, 'foo', {'two_a': 0})
    testtools.zadd(r, 'foo', {'two_b': 0})
    testtools.zadd(r, 'foo', {'three_a': 0})
    assert r.zrevrangebylex('foo', b'+', b'-', 1, 2) == [b'two_a', b'three_a']


def test_zrevrangebylex_raises_error(r):
    testtools.zadd(r, 'foo', {'one_a': 0})
    testtools.zadd(r, 'foo', {'two_a': 0})
    testtools.zadd(r, 'foo', {'two_b': 0})
    testtools.zadd(r, 'foo', {'three_a': 0})

    with pytest.raises(redis.ResponseError):
        r.zrevrangebylex('foo', b'[two_b', b'')

    with pytest.raises(redis.ResponseError):
        r.zrevrangebylex('foo', b'two_b', b'-')

    with pytest.raises(redis.ResponseError):
        r.zrevrangebylex('foo', b'two_b', b'(t')

    with pytest.raises(redis.ResponseError):
        r.zrevrangebylex('foo', b'+', b't')

    with pytest.raises(redis.ResponseError):
        r.zrevrangebylex('foo', b'', b'[two_a')

    with pytest.raises(redis.RedisError):
        r.zrevrangebylex('foo', b'[two_a', b'(two_b', 1)


def test_zrevrangebylex_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zrevrangebylex('foo', b'+', b'-')


def test_zremrangebyrank(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zremrangebyrank('foo', 0, 1) == 2
    assert r.zrange('foo', 0, -1) == [b'three']


def test_zremrangebyrank_negative_indices(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'three': 3})
    assert r.zremrangebyrank('foo', -2, -1) == 2
    assert r.zrange('foo', 0, -1) == [b'one']


def test_zremrangebyrank_out_of_bounds(r):
    testtools.zadd(r, 'foo', {'one': 1})
    assert r.zremrangebyrank('foo', 1, 3) == 0


def test_zremrangebyrank_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zremrangebyrank('foo', 1, 3)


def test_zremrangebyscore(r):
    testtools.zadd(r, 'foo', {'zero': 0})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'four': 4})
    # Outside of range.
    assert r.zremrangebyscore('foo', 5, 10) == 0
    assert r.zrange('foo', 0, -1) == [b'zero', b'two', b'four']
    # Middle of range.
    assert r.zremrangebyscore('foo', 1, 3) == 1
    assert r.zrange('foo', 0, -1) == [b'zero', b'four']
    assert r.zremrangebyscore('foo', 1, 3) == 0
    # Entire range.
    assert r.zremrangebyscore('foo', 0, 4) == 2
    assert r.zrange('foo', 0, -1) == []


def test_zremrangebyscore_exclusive(r):
    testtools.zadd(r, 'foo', {'zero': 0})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'four': 4})
    assert r.zremrangebyscore('foo', '(0', 1) == 0
    assert r.zrange('foo', 0, -1) == [b'zero', b'two', b'four']
    assert r.zremrangebyscore('foo', '-inf', '(0') == 0
    assert r.zrange('foo', 0, -1) == [b'zero', b'two', b'four']
    assert r.zremrangebyscore('foo', '(2', 5) == 1
    assert r.zrange('foo', 0, -1) == [b'zero', b'two']
    assert r.zremrangebyscore('foo', 0, '(2') == 1
    assert r.zrange('foo', 0, -1) == [b'two']
    assert r.zremrangebyscore('foo', '(1', '(3') == 1
    assert r.zrange('foo', 0, -1) == []


def test_zremrangebyscore_raises_error(r):
    testtools.zadd(r, 'foo', {'zero': 0})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'foo', {'four': 4})
    with pytest.raises(redis.ResponseError):
        r.zremrangebyscore('foo', 'three', 1)
    with pytest.raises(redis.ResponseError):
        r.zremrangebyscore('foo', 3, 'one')
    with pytest.raises(redis.ResponseError):
        r.zremrangebyscore('foo', 3, '1)')
    with pytest.raises(redis.ResponseError):
        r.zremrangebyscore('foo', '((3', '1)')


def test_zremrangebyscore_badkey(r):
    assert r.zremrangebyscore('foo', 0, 2) == 0


def test_zremrangebyscore_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zremrangebyscore('foo', 0, 2)


def test_zremrangebylex(r):
    testtools.zadd(r, 'foo', {'two_a': 0})
    testtools.zadd(r, 'foo', {'two_b': 0})
    testtools.zadd(r, 'foo', {'one_a': 0})
    testtools.zadd(r, 'foo', {'three_a': 0})
    assert r.zremrangebylex('foo', b'(three_a', b'[two_b') == 2
    assert r.zremrangebylex('foo', b'(three_a', b'[two_b') == 0
    assert r.zremrangebylex('foo', b'-', b'(o') == 0
    assert r.zremrangebylex('foo', b'-', b'[one_a') == 1
    assert r.zremrangebylex('foo', b'[tw', b'+') == 0
    assert r.zremrangebylex('foo', b'[t', b'+') == 1
    assert r.zremrangebylex('foo', b'[t', b'+') == 0


def test_zremrangebylex_error(r):
    testtools.zadd(r, 'foo', {'two_a': 0})
    testtools.zadd(r, 'foo', {'two_b': 0})
    testtools.zadd(r, 'foo', {'one_a': 0})
    testtools.zadd(r, 'foo', {'three_a': 0})
    with pytest.raises(redis.ResponseError):
        r.zremrangebylex('foo', b'(t', b'two_b')

    with pytest.raises(redis.ResponseError):
        r.zremrangebylex('foo', b't', b'+')

    with pytest.raises(redis.ResponseError):
        r.zremrangebylex('foo', b'[two_a', b'')


def test_zremrangebylex_badkey(r):
    assert r.zremrangebylex('foo', b'(three_a', b'[two_b') == 0


def test_zremrangebylex_wrong_type(r):
    r.sadd('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zremrangebylex('foo', b'bar', b'baz')


def test_zunionstore(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'bar', {'one': 1})
    testtools.zadd(r, 'bar', {'two': 2})
    testtools.zadd(r, 'bar', {'three': 3})
    r.zunionstore('baz', ['foo', 'bar'])
    assert (
            r.zrange('baz', 0, -1, withscores=True)
            == [(b'one', 2), (b'three', 3), (b'two', 4)]
    )


def test_zunionstore_sum(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'bar', {'one': 1})
    testtools.zadd(r, 'bar', {'two': 2})
    testtools.zadd(r, 'bar', {'three': 3})
    r.zunionstore('baz', ['foo', 'bar'], aggregate='SUM')
    assert (
            r.zrange('baz', 0, -1, withscores=True)
            == [(b'one', 2), (b'three', 3), (b'two', 4)]
    )


def test_zunionstore_max(r):
    testtools.zadd(r, 'foo', {'one': 0})
    testtools.zadd(r, 'foo', {'two': 0})
    testtools.zadd(r, 'bar', {'one': 1})
    testtools.zadd(r, 'bar', {'two': 2})
    testtools.zadd(r, 'bar', {'three': 3})
    r.zunionstore('baz', ['foo', 'bar'], aggregate='MAX')
    assert (
            r.zrange('baz', 0, -1, withscores=True)
            == [(b'one', 1), (b'two', 2), (b'three', 3)]
    )


def test_zunionstore_min(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'bar', {'one': 0})
    testtools.zadd(r, 'bar', {'two': 0})
    testtools.zadd(r, 'bar', {'three': 3})
    r.zunionstore('baz', ['foo', 'bar'], aggregate='MIN')
    assert (
            r.zrange('baz', 0, -1, withscores=True)
            == [(b'one', 0), (b'two', 0), (b'three', 3)]
    )


def test_zunionstore_weights(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'bar', {'one': 1})
    testtools.zadd(r, 'bar', {'two': 2})
    testtools.zadd(r, 'bar', {'four': 4})
    r.zunionstore('baz', {'foo': 1, 'bar': 2}, aggregate='SUM')
    assert (
            r.zrange('baz', 0, -1, withscores=True)
            == [(b'one', 3), (b'two', 6), (b'four', 8)]
    )


def test_zunionstore_nan_to_zero(r):
    testtools.zadd(r, 'foo', {'x': math.inf})
    testtools.zadd(r, 'foo2', {'x': math.inf})
    r.zunionstore('bar', OrderedDict([('foo', 1.0), ('foo2', 0.0)]))
    # This is different to test_zinterstore_nan_to_zero because of a quirk
    # in redis. See https://github.com/antirez/redis/issues/3954.
    assert r.zscore('bar', 'x') == math.inf


def test_zunionstore_nan_to_zero2(r):
    testtools.zadd(r, 'foo', {'zero': 0})
    testtools.zadd(r, 'foo2', {'one': 1})
    testtools.zadd(r, 'foo3', {'one': 1})
    r.zunionstore('bar', {'foo': math.inf}, aggregate='SUM')
    assert r.zrange('bar', 0, -1, withscores=True) == [(b'zero', 0)]
    r.zunionstore('bar', OrderedDict([('foo2', math.inf), ('foo3', -math.inf)]))
    assert r.zrange('bar', 0, -1, withscores=True) == [(b'one', 0)]


def test_zunionstore_nan_to_zero_ordering(r):
    testtools.zadd(r, 'foo', {'e1': math.inf})
    testtools.zadd(r, 'bar', {'e1': -math.inf, 'e2': 0.0})
    r.zunionstore('baz', ['foo', 'bar', 'foo'])
    assert r.zscore('baz', 'e1') == 0.0


def test_zunionstore_mixed_set_types(r):
    # No score, redis will use 1.0.
    r.sadd('foo', 'one')
    r.sadd('foo', 'two')
    testtools.zadd(r, 'bar', {'one': 1})
    testtools.zadd(r, 'bar', {'two': 2})
    testtools.zadd(r, 'bar', {'three': 3})
    r.zunionstore('baz', ['foo', 'bar'], aggregate='SUM')
    assert (
            r.zrange('baz', 0, -1, withscores=True)
            == [(b'one', 2), (b'three', 3), (b'two', 3)]
    )


def test_zunionstore_badkey(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    r.zunionstore('baz', ['foo', 'bar'], aggregate='SUM')
    assert r.zrange('baz', 0, -1, withscores=True) == [(b'one', 1), (b'two', 2)]
    r.zunionstore('baz', {'foo': 1, 'bar': 2}, aggregate='SUM')
    assert r.zrange('baz', 0, -1, withscores=True) == [(b'one', 1), (b'two', 2)]


def test_zunionstore_wrong_type(r):
    r.set('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zunionstore('baz', ['foo', 'bar'])


def test_zinterstore(r):
    testtools.zadd(r, 'foo', {'one': 1})
    testtools.zadd(r, 'foo', {'two': 2})
    testtools.zadd(r, 'bar', {'one': 1})
    testtools.zadd(r, 'bar', {'two': 2})
    testtools.zadd(r, 'bar', {'three': 3})
    r.zinterstore('baz', ['foo', 'bar'])
    assert r.zrange('baz', 0, -1, withscores=True) == [(b'one', 2), (b'two', 4)]


def test_zinterstore_mixed_set_types(r):
    r.sadd('foo', 'one')
    r.sadd('foo', 'two')
    testtools.zadd(r, 'bar', {'one': 1})
    testtools.zadd(r, 'bar', {'two': 2})
    testtools.zadd(r, 'bar', {'three': 3})
    r.zinterstore('baz', ['foo', 'bar'], aggregate='SUM')
    assert r.zrange('baz', 0, -1, withscores=True) == [(b'one', 2), (b'two', 3)]


def test_zinterstore_max(r):
    testtools.zadd(r, 'foo', {'one': 0})
    testtools.zadd(r, 'foo', {'two': 0})
    testtools.zadd(r, 'bar', {'one': 1})
    testtools.zadd(r, 'bar', {'two': 2})
    testtools.zadd(r, 'bar', {'three': 3})
    r.zinterstore('baz', ['foo', 'bar'], aggregate='MAX')
    assert r.zrange('baz', 0, -1, withscores=True) == [(b'one', 1), (b'two', 2)]


def test_zinterstore_onekey(r):
    testtools.zadd(r, 'foo', {'one': 1})
    r.zinterstore('baz', ['foo'], aggregate='MAX')
    assert r.zrange('baz', 0, -1, withscores=True) == [(b'one', 1)]


def test_zinterstore_nokey(r):
    with pytest.raises(redis.ResponseError):
        r.zinterstore('baz', [], aggregate='MAX')


def test_zinterstore_nan_to_zero(r):
    testtools.zadd(r, 'foo', {'x': math.inf})
    testtools.zadd(r, 'foo2', {'x': math.inf})
    r.zinterstore('bar', OrderedDict([('foo', 1.0), ('foo2', 0.0)]))
    assert r.zscore('bar', 'x') == 0.0


def test_zunionstore_nokey(r):
    with pytest.raises(redis.ResponseError):
        r.zunionstore('baz', [], aggregate='MAX')


def test_zinterstore_wrong_type(r):
    r.set('foo', 'bar')
    with pytest.raises(redis.ResponseError):
        r.zinterstore('baz', ['foo', 'bar'])


def test_empty_zset(r):
    testtools.zadd(r, 'foo', {'one': 1})
    r.zrem('foo', 'one')
    assert not r.exists('foo')


def test_multidb(r, create_redis):
    r1 = create_redis(db=0)
    r2 = create_redis(db=1)

    r1['r1'] = 'r1'
    r2['r2'] = 'r2'

    assert 'r2' not in r1
    assert 'r1' not in r2

    assert r1['r1'] == b'r1'
    assert r2['r2'] == b'r2'

    assert r1.flushall() is True

    assert 'r1' not in r1
    assert 'r2' not in r2


def test_basic_sort(r):
    r.rpush('foo', '2')
    r.rpush('foo', '1')
    r.rpush('foo', '3')

    assert r.sort('foo') == [b'1', b'2', b'3']


def test_pipeline(r):
    # The pipeline method returns an object for
    # issuing multiple commands in a batch.
    p = r.pipeline()
    p.watch('bam')
    p.multi()
    p.set('foo', 'bar').get('foo')
    p.lpush('baz', 'quux')
    p.lpush('baz', 'quux2').lrange('baz', 0, -1)
    res = p.execute()

    # Check return values returned as list.
    assert res == [True, b'bar', 1, 2, [b'quux2', b'quux']]

    # Check side effects happened as expected.
    assert r.lrange('baz', 0, -1) == [b'quux2', b'quux']

    # Check that the command buffer has been emptied.
    assert p.execute() == []


def test_pipeline_ignore_errors(r):
    """Test the pipeline ignoring errors when asked."""
    with r.pipeline() as p:
        p.set('foo', 'bar')
        p.rename('baz', 'bats')
        with pytest.raises(redis.exceptions.ResponseError):
            p.execute()
        assert [] == p.execute()
    with r.pipeline() as p:
        p.set('foo', 'bar')
        p.rename('baz', 'bats')
        res = p.execute(raise_on_error=False)

        assert [] == p.execute()

        assert len(res) == 2
        assert isinstance(res[1], redis.exceptions.ResponseError)


def test_multiple_successful_watch_calls(r):
    p = r.pipeline()
    p.watch('bam')
    p.multi()
    p.set('foo', 'bar')
    # Check that the watched keys buffer has been emptied.
    p.execute()

    # bam is no longer being watched, so it's ok to modify
    # it now.
    p.watch('foo')
    r.set('bam', 'boo')
    p.multi()
    p.set('foo', 'bats')
    assert p.execute() == [True]


def test_pipeline_non_transactional(r):
    # For our simple-minded model I don't think
    # there is any observable difference.
    p = r.pipeline(transaction=False)
    res = p.set('baz', 'quux').get('baz').execute()

    assert res == [True, b'quux']


def test_pipeline_raises_when_watched_key_changed(r):
    r.set('foo', 'bar')
    r.rpush('greet', 'hello')
    p = r.pipeline()
    try:
        p.watch('greet', 'foo')
        nextf = bytes(p.get('foo')) + b'baz'
        # Simulate change happening on another thread.
        r.rpush('greet', 'world')
        # Begin pipelining.
        p.multi()
        p.set('foo', nextf)

        with pytest.raises(redis.WatchError):
            p.execute()
    finally:
        p.reset()


def test_pipeline_succeeds_despite_unwatched_key_changed(r):
    # Same setup as before except for the params to the WATCH command.
    r.set('foo', 'bar')
    r.rpush('greet', 'hello')
    p = r.pipeline()
    try:
        # Only watch one of the 2 keys.
        p.watch('foo')
        nextf = bytes(p.get('foo')) + b'baz'
        # Simulate change happening on another thread.
        r.rpush('greet', 'world')
        p.multi()
        p.set('foo', nextf)
        p.execute()

        # Check the commands were executed.
        assert r.get('foo') == b'barbaz'
    finally:
        p.reset()


def test_pipeline_succeeds_when_watching_nonexistent_key(r):
    r.set('foo', 'bar')
    r.rpush('greet', 'hello')
    p = r.pipeline()
    try:
        # Also watch a nonexistent key.
        p.watch('foo', 'bam')
        nextf = bytes(p.get('foo')) + b'baz'
        # Simulate change happening on another thread.
        r.rpush('greet', 'world')
        p.multi()
        p.set('foo', nextf)
        p.execute()

        # Check the commands were executed.
        assert r.get('foo') == b'barbaz'
    finally:
        p.reset()


def test_watch_state_is_cleared_across_multiple_watches(r):
    r.set('foo', 'one')
    r.set('bar', 'baz')
    p = r.pipeline()

    try:
        p.watch('foo')
        # Simulate change happening on another thread.
        r.set('foo', 'three')
        p.multi()
        p.set('foo', 'three')
        with pytest.raises(redis.WatchError):
            p.execute()

        # Now watch another key.  It should be ok to change
        # foo as we're no longer watching it.
        p.watch('bar')
        r.set('foo', 'four')
        p.multi()
        p.set('bar', 'five')
        assert p.execute() == [True]
    finally:
        p.reset()


def test_watch_state_is_cleared_after_abort(r):
    # redis-py's pipeline handling and connection pooling interferes with this
    # test, so raw commands are used instead.
    raw_command(r, 'watch', 'foo')
    raw_command(r, 'multi')
    with pytest.raises(redis.ResponseError):
        raw_command(r, 'mget')  # Wrong number of arguments
    with pytest.raises(redis.exceptions.ExecAbortError):
        raw_command(r, 'exec')

    raw_command(r, 'set', 'foo', 'bar')  # Should NOT trigger the watch from earlier
    raw_command(r, 'multi')
    raw_command(r, 'set', 'abc', 'done')
    raw_command(r, 'exec')

    assert r.get('abc') == b'done'


def test_pipeline_transaction_shortcut(r):
    # This example taken pretty much from the redis-py documentation.
    r.set('OUR-SEQUENCE-KEY', 13)
    calls = []

    def client_side_incr(pipe):
        calls.append((pipe,))
        current_value = pipe.get('OUR-SEQUENCE-KEY')
        next_value = int(current_value) + 1

        if len(calls) < 3:
            # Simulate a change from another thread.
            r.set('OUR-SEQUENCE-KEY', next_value)

        pipe.multi()
        pipe.set('OUR-SEQUENCE-KEY', next_value)

    res = r.transaction(client_side_incr, 'OUR-SEQUENCE-KEY')

    assert res == [True]
    assert int(r.get('OUR-SEQUENCE-KEY')) == 16
    assert len(calls) == 3


def test_pipeline_transaction_value_from_callable(r):
    def callback(pipe):
        # No need to do anything here since we only want the return value
        return 'OUR-RETURN-VALUE'

    res = r.transaction(callback, 'OUR-SEQUENCE-KEY', value_from_callable=True)
    assert res == 'OUR-RETURN-VALUE'


def test_pipeline_empty(r):
    p = r.pipeline()
    assert len(p) == 0


def test_pipeline_length(r):
    p = r.pipeline()
    p.set('baz', 'quux').get('baz')
    assert len(p) == 2


def test_pipeline_no_commands(r):
    # Prior to 3.4, redis-py's execute is a nop if there are no commands
    # queued, so it succeeds even if watched keys have been changed.
    r.set('foo', '1')
    p = r.pipeline()
    p.watch('foo')
    r.set('foo', '2')
    with pytest.raises(redis.WatchError):
        p.execute()


def test_pipeline_failed_transaction(r):
    p = r.pipeline()
    p.multi()
    p.set('foo', 'bar')
    # Deliberately induce a syntax error
    p.execute_command('set')
    # It should be an ExecAbortError, but redis-py tries to DISCARD after the
    # failed EXEC, which raises a ResponseError.
    with pytest.raises(redis.ResponseError):
        p.execute()
    assert not r.exists('foo')


def test_pipeline_srem_no_change(r):
    # A regression test for a case picked up by hypothesis tests.
    p = r.pipeline()
    p.watch('foo')
    r.srem('foo', 'bar')
    p.multi()
    p.set('foo', 'baz')
    p.execute()
    assert r.get('foo') == b'baz'


# The behaviour changed in redis 6.0 (see https://github.com/redis/redis/issues/6594).
@pytest.mark.min_server('6.0')
def test_pipeline_move(r):
    # A regression test for a case picked up by hypothesis tests.
    r.set('foo', 'bar')
    p = r.pipeline()
    p.watch('foo')
    r.move('foo', 1)
    # Ensure the transaction isn't empty, which had different behaviour in
    # older versions of redis-py.
    p.multi()
    p.set('bar', 'baz')
    with pytest.raises(redis.exceptions.WatchError):
        p.execute()


@pytest.mark.min_server('6.0.6')
def test_exec_bad_arguments(r):
    # Redis 6.0.6 changed the behaviour of exec so that it always fails with
    # EXECABORT, even when it's just bad syntax.
    with pytest.raises(redis.exceptions.ExecAbortError):
        r.execute_command('exec', 'blahblah')


@pytest.mark.min_server('6.0.6')
def test_exec_bad_arguments_abort(r):
    r.execute_command('multi')
    with pytest.raises(redis.exceptions.ExecAbortError):
        r.execute_command('exec', 'blahblah')
    # Should have aborted the transaction, so we can run another one
    p = r.pipeline()
    p.multi()
    p.set('bar', 'baz')
    p.execute()
    assert r.get('bar') == b'baz'


def test_key_patterns(r):
    r.mset({'one': 1, 'two': 2, 'three': 3, 'four': 4})
    assert sorted(r.keys('*o*')) == [b'four', b'one', b'two']
    assert r.keys('t??') == [b'two']
    assert sorted(r.keys('*')) == [b'four', b'one', b'three', b'two']
    assert sorted(r.keys()) == [b'four', b'one', b'three', b'two']


@testtools.run_test_if_redispy_ver('above', '3')
def test_ping_pubsub(r):
    p = r.pubsub()
    p.subscribe('channel')
    p.parse_response()  # Consume the subscribe reply
    p.ping()
    assert p.parse_response() == [b'pong', b'']
    p.ping('test')
    assert p.parse_response() == [b'pong', b'test']


@pytest.mark.slow
def test_pubsub_subscribe(r):
    pubsub = r.pubsub()
    pubsub.subscribe("channel")
    sleep(1)
    expected_message = {'type': 'subscribe', 'pattern': None,
                        'channel': b'channel', 'data': 1}
    message = pubsub.get_message()
    keys = list(pubsub.channels.keys())

    key = keys[0]
    key = (key if type(key) == bytes
           else bytes(key, encoding='utf-8'))

    assert len(keys) == 1
    assert key == b'channel'
    assert message == expected_message


@pytest.mark.slow
def test_pubsub_psubscribe(r):
    pubsub = r.pubsub()
    pubsub.psubscribe("channel.*")
    sleep(1)
    expected_message = {'type': 'psubscribe', 'pattern': None,
                        'channel': b'channel.*', 'data': 1}

    message = pubsub.get_message()
    keys = list(pubsub.patterns.keys())
    assert len(keys) == 1
    assert message == expected_message


@pytest.mark.slow
def test_pubsub_unsubscribe(r):
    pubsub = r.pubsub()
    pubsub.subscribe('channel-1', 'channel-2', 'channel-3')
    sleep(1)
    expected_message = {'type': 'unsubscribe', 'pattern': None,
                        'channel': b'channel-1', 'data': 2}
    pubsub.get_message()
    pubsub.get_message()
    pubsub.get_message()

    # unsubscribe from one
    pubsub.unsubscribe('channel-1')
    sleep(1)
    message = pubsub.get_message()
    keys = list(pubsub.channels.keys())
    assert message == expected_message
    assert len(keys) == 2

    # unsubscribe from multiple
    pubsub.unsubscribe()
    sleep(1)
    pubsub.get_message()
    pubsub.get_message()
    keys = list(pubsub.channels.keys())
    assert message == expected_message
    assert len(keys) == 0


@pytest.mark.slow
def test_pubsub_punsubscribe(r):
    pubsub = r.pubsub()
    pubsub.psubscribe('channel-1.*', 'channel-2.*', 'channel-3.*')
    sleep(1)
    expected_message = {'type': 'punsubscribe', 'pattern': None,
                        'channel': b'channel-1.*', 'data': 2}
    pubsub.get_message()
    pubsub.get_message()
    pubsub.get_message()

    # unsubscribe from one
    pubsub.punsubscribe('channel-1.*')
    sleep(1)
    message = pubsub.get_message()
    keys = list(pubsub.patterns.keys())
    assert message == expected_message
    assert len(keys) == 2

    # unsubscribe from multiple
    pubsub.punsubscribe()
    sleep(1)
    pubsub.get_message()
    pubsub.get_message()
    keys = list(pubsub.patterns.keys())
    assert len(keys) == 0


@pytest.mark.slow
def test_pubsub_listen(r):
    def _listen(pubsub, q):
        count = 0
        for message in pubsub.listen():
            q.put(message)
            count += 1
            if count == 4:
                pubsub.close()

    channel = 'ch1'
    patterns = ['ch1*', 'ch[1]', 'ch?']
    pubsub = r.pubsub()
    pubsub.subscribe(channel)
    pubsub.psubscribe(*patterns)
    sleep(1)
    msg1 = pubsub.get_message()
    msg2 = pubsub.get_message()
    msg3 = pubsub.get_message()
    msg4 = pubsub.get_message()
    assert msg1['type'] == 'subscribe'
    assert msg2['type'] == 'psubscribe'
    assert msg3['type'] == 'psubscribe'
    assert msg4['type'] == 'psubscribe'

    q = Queue()
    t = threading.Thread(target=_listen, args=(pubsub, q))
    t.start()
    msg = 'hello world'
    r.publish(channel, msg)
    t.join()

    msg1 = q.get()
    msg2 = q.get()
    msg3 = q.get()
    msg4 = q.get()

    bpatterns = [pattern.encode() for pattern in patterns]
    bpatterns.append(channel.encode())
    msg = msg.encode()
    assert msg1['data'] == msg
    assert msg1['channel'] in bpatterns
    assert msg2['data'] == msg
    assert msg2['channel'] in bpatterns
    assert msg3['data'] == msg
    assert msg3['channel'] in bpatterns
    assert msg4['data'] == msg
    assert msg4['channel'] in bpatterns


@pytest.mark.slow
def test_pubsub_listen_handler(r):
    def _handler(message):
        calls.append(message)

    channel = 'ch1'
    patterns = {'ch?': _handler}
    calls = []

    pubsub = r.pubsub()
    pubsub.subscribe(ch1=_handler)
    pubsub.psubscribe(**patterns)
    sleep(1)
    msg1 = pubsub.get_message()
    msg2 = pubsub.get_message()
    assert msg1['type'] == 'subscribe'
    assert msg2['type'] == 'psubscribe'
    msg = 'hello world'
    r.publish(channel, msg)
    sleep(1)
    for i in range(2):
        msg = pubsub.get_message()
        assert msg is None  # get_message returns None when handler is used
    pubsub.close()
    calls.sort(key=lambda call: call['type'])
    assert calls == [
        {'pattern': None, 'channel': b'ch1', 'data': b'hello world', 'type': 'message'},
        {'pattern': b'ch?', 'channel': b'ch1', 'data': b'hello world', 'type': 'pmessage'}
    ]


@pytest.mark.slow
def test_pubsub_ignore_sub_messages_listen(r):
    def _listen(pubsub, q):
        count = 0
        for message in pubsub.listen():
            q.put(message)
            count += 1
            if count == 4:
                pubsub.close()

    channel = 'ch1'
    patterns = ['ch1*', 'ch[1]', 'ch?']
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(channel)
    pubsub.psubscribe(*patterns)
    sleep(1)

    q = Queue()
    t = threading.Thread(target=_listen, args=(pubsub, q))
    t.start()
    msg = 'hello world'
    r.publish(channel, msg)
    t.join()

    msg1 = q.get()
    msg2 = q.get()
    msg3 = q.get()
    msg4 = q.get()

    bpatterns = [pattern.encode() for pattern in patterns]
    bpatterns.append(channel.encode())
    msg = msg.encode()
    assert msg1['data'] == msg
    assert msg1['channel'] in bpatterns
    assert msg2['data'] == msg
    assert msg2['channel'] in bpatterns
    assert msg3['data'] == msg
    assert msg3['channel'] in bpatterns
    assert msg4['data'] == msg
    assert msg4['channel'] in bpatterns


@pytest.mark.slow
def test_pubsub_binary(r):
    def _listen(pubsub, q):
        for message in pubsub.listen():
            q.put(message)
            pubsub.close()

    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe('channel\r\n\xff')
    sleep(1)

    q = Queue()
    t = threading.Thread(target=_listen, args=(pubsub, q))
    t.start()
    msg = b'\x00hello world\r\n\xff'
    r.publish('channel\r\n\xff', msg)
    t.join()

    received = q.get()
    assert received['data'] == msg


@pytest.mark.slow
def test_pubsub_run_in_thread(r):
    q = Queue()

    pubsub = r.pubsub()
    pubsub.subscribe(channel=q.put)
    pubsub_thread = pubsub.run_in_thread()

    msg = b"Hello World"
    r.publish("channel", msg)

    retrieved = q.get()
    assert retrieved["data"] == msg

    pubsub_thread.stop()
    # Newer versions of redis wait for an unsubscribe message, which sometimes comes early
    # https://github.com/andymccurdy/redis-py/issues/1150
    if pubsub.channels:
        pubsub.channels = {}
    pubsub_thread.join()
    assert not pubsub_thread.is_alive()

    pubsub.subscribe(channel=None)
    with pytest.raises(redis.exceptions.PubSubError):
        pubsub_thread = pubsub.run_in_thread()

    pubsub.unsubscribe("channel")

    pubsub.psubscribe(channel=None)
    with pytest.raises(redis.exceptions.PubSubError):
        pubsub_thread = pubsub.run_in_thread()


@pytest.mark.slow
@pytest.mark.parametrize(
    "timeout_value",
    [
        1,
        pytest.param(
            None,
            marks=testtools.run_test_if_redispy_ver('above', '3.2')
        )
    ]
)
def test_pubsub_timeout(r, timeout_value):
    def publish():
        sleep(0.1)
        r.publish('channel', 'hello')

    p = r.pubsub()
    p.subscribe('channel')
    p.parse_response()  # Drains the subscribe message
    publish_thread = threading.Thread(target=publish)
    publish_thread.start()
    message = p.get_message(timeout=timeout_value)
    assert message == {
        'type': 'message', 'pattern': None,
        'channel': b'channel', 'data': b'hello'
    }
    publish_thread.join()

    if timeout_value is not None:
        # For infinite timeout case don't wait for the message that will never appear.
        message = p.get_message(timeout=timeout_value)
        assert message is None


def test_pfadd(r):
    key = "hll-pfadd"
    assert r.pfadd(key, "a", "b", "c", "d", "e", "f", "g") == 1
    assert r.pfcount(key) == 7


def test_pfcount(r):
    key1 = "hll-pfcount01"
    key2 = "hll-pfcount02"
    key3 = "hll-pfcount03"
    assert r.pfadd(key1, "foo", "bar", "zap") == 1
    assert r.pfadd(key1, "zap", "zap", "zap") == 0
    assert r.pfadd(key1, "foo", "bar") == 0
    assert r.pfcount(key1) == 3
    assert r.pfadd(key2, "1", "2", "3") == 1
    assert r.pfcount(key2) == 3
    assert r.pfcount(key1, key2) == 6
    assert r.pfadd(key3, "foo", "bar", "zip") == 1
    assert r.pfcount(key3) == 3
    assert r.pfcount(key1, key3) == 4
    assert r.pfcount(key1, key2, key3) == 7


def test_pfmerge(r):
    key1 = "hll-pfmerge01"
    key2 = "hll-pfmerge02"
    key3 = "hll-pfmerge03"
    assert r.pfadd(key1, "foo", "bar", "zap", "a") == 1
    assert r.pfadd(key2, "a", "b", "c", "foo") == 1
    assert r.pfmerge(key3, key1, key2)
    assert r.pfcount(key3) == 6


def test_sscan(r):
    # Setup the data
    name = 'sscan-test'
    for ix in range(20):
        k = 'sscan-test:%s' % ix
        r.sadd(name, k)
    expected = r.smembers(name)
    assert len(expected) == 20  # Ensure we know what we're testing

    # Test that we page through the results and get everything out
    results = []
    cursor = '0'
    while cursor != 0:
        cursor, data = r.sscan(name, cursor, count=6)
        results.extend(data)
    assert set(expected) == set(results)

    # Test the iterator version
    results = [r for r in r.sscan_iter(name, count=6)]
    assert set(expected) == set(results)

    # Now test that the MATCH functionality works
    results = []
    cursor = '0'
    while cursor != 0:
        cursor, data = r.sscan(name, cursor, match='*7', count=100)
        results.extend(data)
    assert b'sscan-test:7' in results
    assert b'sscan-test:17' in results
    assert len(results) == 2

    # Test the match on iterator
    results = [r for r in r.sscan_iter(name, match='*7')]
    assert b'sscan-test:7' in results
    assert b'sscan-test:17' in results
    assert len(results) == 2


def test_hscan(r):
    # Setup the data
    name = 'hscan-test'
    for ix in range(20):
        k = 'key:%s' % ix
        v = 'result:%s' % ix
        r.hset(name, k, v)
    expected = r.hgetall(name)
    assert len(expected) == 20  # Ensure we know what we're testing

    # Test that we page through the results and get everything out
    results = {}
    cursor = '0'
    while cursor != 0:
        cursor, data = r.hscan(name, cursor, count=6)
        results.update(data)
    assert expected == results

    # Test the iterator version
    results = {}
    for key, val in r.hscan_iter(name, count=6):
        results[key] = val
    assert expected == results

    # Now test that the MATCH functionality works
    results = {}
    cursor = '0'
    while cursor != 0:
        cursor, data = r.hscan(name, cursor, match='*7', count=100)
        results.update(data)
    assert b'key:7' in results
    assert b'key:17' in results
    assert len(results) == 2

    # Test the match on iterator
    results = {}
    for key, val in r.hscan_iter(name, match='*7'):
        results[key] = val
    assert b'key:7' in results
    assert b'key:17' in results
    assert len(results) == 2


def test_zscan(r):
    # Setup the data
    name = 'zscan-test'
    for ix in range(20):
        testtools.zadd(r, name, {'key:%s' % ix: ix})
    expected = dict(r.zrange(name, 0, -1, withscores=True))

    # Test the basic version
    results = {}
    for key, val in r.zscan_iter(name, count=6):
        results[key] = val
    assert results == expected

    # Now test that the MATCH functionality works
    results = {}
    cursor = '0'
    while cursor != 0:
        cursor, data = r.zscan(name, cursor, match='*7', count=6)
        results.update(data)
    assert results == {b'key:7': 7.0, b'key:17': 17.0}


@pytest.mark.slow
def test_set_ex_should_expire_value(r):
    r.set('foo', 'bar')
    assert r.get('foo') == b'bar'
    r.set('foo', 'bar', ex=1)
    sleep(2)
    assert r.get('foo') is None


@pytest.mark.slow
def test_set_px_should_expire_value(r):
    r.set('foo', 'bar', px=500)
    sleep(1.5)
    assert r.get('foo') is None


@pytest.mark.slow
def test_psetex_expire_value(r):
    with pytest.raises(ResponseError):
        r.psetex('foo', 0, 'bar')
    r.psetex('foo', 500, 'bar')
    sleep(1.5)
    assert r.get('foo') is None


@pytest.mark.slow
def test_psetex_expire_value_using_timedelta(r):
    with pytest.raises(ResponseError):
        r.psetex('foo', timedelta(seconds=0), 'bar')
    r.psetex('foo', timedelta(seconds=0.5), 'bar')
    sleep(1.5)
    assert r.get('foo') is None


@pytest.mark.max_server('6.2.7')
def test_script_exists(r):
    # test response for no arguments by bypassing the py-redis command
    # as it requires at least one argument
    assert raw_command(r, "SCRIPT EXISTS") == []

    # use single character characters for non-existing scripts, as those
    # will never be equal to an actual sha1 hash digest
    assert r.script_exists("a") == [0]
    assert r.script_exists("a", "b", "c", "d", "e", "f") == [0, 0, 0, 0, 0, 0]

    sha1_one = r.script_load("return 'a'")
    assert r.script_exists(sha1_one) == [1]
    assert r.script_exists(sha1_one, "a") == [1, 0]
    assert r.script_exists("a", "b", "c", sha1_one, "e") == [0, 0, 0, 1, 0]

    sha1_two = r.script_load("return 'b'")
    assert r.script_exists(sha1_one, sha1_two) == [1, 1]
    assert r.script_exists("a", sha1_one, "c", sha1_two, "e", "f") == [0, 1, 0, 1, 0, 0]


@pytest.mark.parametrize("args", [("a",), tuple("abcdefghijklmn")])
def test_script_flush_errors_with_args(r, args):
    with pytest.raises(redis.ResponseError):
        raw_command(r, "SCRIPT FLUSH %s" % " ".join(args))


def test_script_flush(r):
    # generate/load six unique scripts and store their sha1 hash values
    sha1_values = [r.script_load("return '%s'" % char) for char in "abcdef"]

    # assert the scripts all exist prior to flushing
    assert r.script_exists(*sha1_values) == [1] * len(sha1_values)

    # flush and assert OK response
    assert r.script_flush() is True

    # assert none of the scripts exists after flushing
    assert r.script_exists(*sha1_values) == [0] * len(sha1_values)


@testtools.run_test_if_redispy_ver('above', '3.4')
@pytest.mark.fake
def test_socket_cleanup_pubsub(fake_server):
    r1 = fakeredis.FakeStrictRedis(server=fake_server)
    r2 = fakeredis.FakeStrictRedis(server=fake_server)
    ps = r1.pubsub()
    with ps:
        ps.subscribe('test')
        ps.psubscribe('test*')
    r2.publish('test', 'foo')


@pytest.mark.fake
def test_socket_cleanup_watch(fake_server):
    r1 = fakeredis.FakeStrictRedis(server=fake_server)
    r2 = fakeredis.FakeStrictRedis(server=fake_server)
    pipeline = r1.pipeline(transaction=False)
    # This needs some poking into redis-py internals to ensure that we reach
    # FakeSocket._cleanup. We need to close the socket while there is still
    # a watch in place, but not allow it to be garbage collected (hence we
    # set 'sock' even though it is unused).
    with pipeline:
        pipeline.watch('test')
        sock = pipeline.connection._sock  # noqa: F841
        pipeline.connection.disconnect()
    r2.set('test', 'foo')

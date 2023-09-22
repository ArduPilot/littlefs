#!/usr/bin/env python3

import bisect
import collections as co
import functools as ft
import itertools as it
import math as m
import os
import struct


TAG_NULL        = 0x0000
TAG_CONFIG      = 0x0000
TAG_MAGIC       = 0x0003
TAG_VERSION     = 0x0004
TAG_FLAGS       = 0x0005
TAG_CKSUMTYPE   = 0x0006
TAG_REDUNDTYPE  = 0x0007
TAG_BLOCKLIMIT  = 0x0008
TAG_DISKLIMIT   = 0x0009
TAG_MLEAFLIMIT  = 0x000a
TAG_SIZELIMIT   = 0x000b
TAG_NAMELIMIT   = 0x000c
TAG_UTAGLIMIT   = 0x000d
TAG_UATTRLIMIT  = 0x000e
TAG_GSTATE      = 0x0100
TAG_GRM         = 0x0100
TAG_NAME        = 0x0200
TAG_BRANCH      = 0x0200
TAG_BOOKMARK    = 0x0201
TAG_REG         = 0x0202
TAG_DIR         = 0x0203
TAG_STRUCT      = 0x0300
TAG_INLINED     = 0x0300
TAG_TRUNK       = 0x0304
TAG_BLOCK       = 0x0308
TAG_BTREE       = 0x030c
TAG_MDIR        = 0x0311
TAG_MTREE       = 0x0314
TAG_MROOT       = 0x0318
TAG_DID         = 0x031c
TAG_UATTR       = 0x0400
TAG_SATTR       = 0x0600
TAG_SHRUB       = 0x1000
TAG_CKSUM       = 0x2000
TAG_ECKSUM      = 0x2100
TAG_ALT         = 0x4000
TAG_GT          = 0x2000
TAG_R           = 0x1000


# parse some rbyd addr encodings
# 0xa     -> [0xa]
# 0xa.b   -> ([0xa], b)
# 0x{a,b} -> [0xa, 0xb]
def rbydaddr(s):
    s = s.strip()
    b = 10
    if s.startswith('0x') or s.startswith('0X'):
        s = s[2:]
        b = 16
    elif s.startswith('0o') or s.startswith('0O'):
        s = s[2:]
        b = 8
    elif s.startswith('0b') or s.startswith('0B'):
        s = s[2:]
        b = 2

    trunk = None
    if '.' in s:
        s, s_ = s.split('.', 1)
        trunk = int(s_, b)

    if s.startswith('{') and '}' in s:
        ss = s[1:s.find('}')].split(',')
    else:
        ss = [s]

    addr = []
    for s in ss:
        if trunk is not None:
            addr.append((int(s, b), trunk))
        else:
            addr.append(int(s, b))

    return addr

def crc32c(data, crc=0):
    crc ^= 0xffffffff
    for b in data:
        crc ^= b
        for j in range(8):
            crc = (crc >> 1) ^ ((crc & 1) * 0x82f63b78)
    return 0xffffffff ^ crc

def fromle32(data):
    return struct.unpack('<I', data[0:4].ljust(4, b'\0'))[0]

def fromleb128(data):
    word = 0
    for i, b in enumerate(data):
        word |= ((b & 0x7f) << 7*i)
        word &= 0xffffffff
        if not b & 0x80:
            return word, i+1
    return word, len(data)

def fromtag(data):
    data = data.ljust(4, b'\0')
    tag = (data[0] << 8) | data[1]
    weight, d = fromleb128(data[2:])
    size, d_ = fromleb128(data[2+d:])
    return tag>>15, tag&0x7fff, weight, size, 2+d+d_

def frommdir(data):
    blocks = []
    d = 0
    while d < len(data):
        block, d_ = fromleb128(data[d:])
        blocks.append(block)
        d += d_
    return blocks

def frombtree(data):
    d = 0
    block, d_ = fromleb128(data[d:]); d += d_
    trunk, d_ = fromleb128(data[d:]); d += d_
    w, d_ = fromleb128(data[d:]); d += d_
    cksum = fromle32(data[d:]); d += 4
    return block, trunk, w, cksum

def popc(x):
    return bin(x).count('1')

def xxd(data, width=16):
    for i in range(0, len(data), width):
        yield '%-*s %-*s' % (
            3*width,
            ' '.join('%02x' % b for b in data[i:i+width]),
            width,
            ''.join(
                b if b >= ' ' and b <= '~' else '.'
                for b in map(chr, data[i:i+width])))

def tagrepr(tag, w, size, off=None):
    if (tag & 0xefff) == TAG_NULL:
        return '%snull%s%s' % (
            'shrub' if tag & TAG_SHRUB else '',
            ' w%d' % w if w else '',
            ' %d' % size if size else '')
    elif (tag & 0xef00) == TAG_CONFIG:
        return '%s%s%s %d' % (
            'shrub' if tag & TAG_SHRUB else '',
            'magic' if (tag & 0xfff) == TAG_MAGIC
                else 'version' if (tag & 0xfff) == TAG_VERSION
                else 'flags' if (tag & 0xfff) == TAG_FLAGS
                else 'cksumtype' if (tag & 0xfff) == TAG_CKSUMTYPE
                else 'redundtype' if (tag & 0xfff) == TAG_REDUNDTYPE
                else 'blocklimit' if (tag & 0xfff) == TAG_BLOCKLIMIT
                else 'disklimit' if (tag & 0xfff) == TAG_DISKLIMIT
                else 'mleaflimit' if (tag & 0xfff) == TAG_MLEAFLIMIT
                else 'sizelimit' if (tag & 0xfff) == TAG_SIZELIMIT
                else 'namelimit' if (tag & 0xfff) == TAG_NAMELIMIT
                else 'utaglimit' if (tag & 0xfff) == TAG_UTAGLIMIT
                else 'uattrlimit' if (tag & 0xfff) == TAG_UATTRLIMIT
                else 'config 0x%02x' % (tag & 0xff),
            ' w%d' % w if w else '',
            size)
    elif (tag & 0xef00) == TAG_GSTATE:
        return '%s%s%s %d' % (
            'shrub' if tag & TAG_SHRUB else '',
            'grm' if (tag & 0xfff) == TAG_GRM
                else 'gstate 0x%02x' % (tag & 0xff),
            ' w%d' % w if w else '',
            size)
    elif (tag & 0xef00) == TAG_NAME:
        return '%s%s%s %d' % (
            'shrub' if tag & TAG_SHRUB else '',
            'branch' if (tag & 0xfff) == TAG_BRANCH
                else 'bookmark' if (tag & 0xfff) == TAG_BOOKMARK
                else 'reg' if (tag & 0xfff) == TAG_REG
                else 'dir' if (tag & 0xfff) == TAG_DIR
                else 'name 0x%02x' % (tag & 0xff),
            ' w%d' % w if w else '',
            size)
    elif (tag & 0xef00) == TAG_STRUCT:
        return '%s%s%s %d' % (
            'shrub' if tag & TAG_SHRUB else '',
            'inlined' if (tag & 0xfff) == TAG_INLINED
                else 'trunk' if (tag & 0xfff) == TAG_TRUNK
                else 'block' if (tag & 0xfff) == TAG_BLOCK
                else 'btree' if (tag & 0xfff) == TAG_BTREE
                else 'mdir' if (tag & 0xfff) == TAG_MDIR
                else 'mtree' if (tag & 0xfff) == TAG_MTREE
                else 'mroot' if (tag & 0xfff) == TAG_MROOT
                else 'did' if (tag & 0xfff) == TAG_DID
                else 'struct 0x%02x' % (tag & 0xff),
            ' w%d' % w if w else '',
            size)
    elif (tag & 0xef00) == TAG_UATTR:
        return '%suattr 0x%02x%s %d' % (
            'shrub' if tag & TAG_SHRUB else '',
            ((tag & 0x100) >> 1) | (tag & 0xff),
            ' w%d' % w if w else '',
            size)
    elif (tag & 0xef00) == TAG_SATTR:
        return '%ssattr 0x%02x%s %d' % (
            'shrub' if tag & TAG_SHRUB else '',
            ((tag & 0x100) >> 1) | (tag & 0xff),
            ' w%d' % w if w else '',
            size)
    elif (tag & 0xff00) == TAG_CKSUM:
        return 'cksum 0x%02x%s %d' % (
            tag & 0xff,
            ' w%d' % w if w > 0 else '',
            size)
    elif (tag & 0xff00) == TAG_ECKSUM:
        return 'ecksum%s%s %d' % (
            ' 0x%02x' % (tag & 0xff) if tag & 0xff else '',
            ' w%d' % w if w > 0 else '',
            size)
    elif tag & TAG_ALT:
        return 'alt%s%s 0x%x w%d %s' % (
            'r' if tag & TAG_R else 'b',
            'gt' if tag & TAG_GT else 'le',
            tag & 0x0fff,
            w,
            '0x%x' % (0xffffffff & (off-size))
                if off is not None
                else '-%d' % off)
    else:
        return '0x%04x w%d %d' % (tag, w, size)


# our core rbyd type
class Rbyd:
    def __init__(self, block, data, rev, eoff, trunk, weight):
        self.block = block
        self.data = data
        self.rev = rev
        self.eoff = eoff
        self.trunk = trunk
        self.weight = weight
        self.redund_blocks = []

    def addr(self):
        if not self.redund_blocks:
            return '0x%x.%x' % (self.block, self.trunk)
        else:
            return '0x{%x,%s}.%x' % (
                self.block,
                ','.join('%x' % block for block in self.redund_blocks),
                self.trunk)

    @classmethod
    def fetch(cls, f, block_size, blocks, trunk=None):
        if isinstance(blocks, int):
            blocks = [blocks]

        if len(blocks) > 1:
            # fetch all blocks
            rbyds = [cls.fetch(f, block_size, block, trunk) for block in blocks]
            # determine most recent revision
            i = 0
            for i_, rbyd in enumerate(rbyds):
                # compare with sequence arithmetic
                if rbyd and (
                        not rbyds[i]
                        or not ((rbyd.rev - rbyds[i].rev) & 0x80000000)
                        or (rbyd.rev == rbyds[i].rev
                            and rbyd.trunk > rbyds[i].trunk)):
                    i = i_
            # keep track of the other blocks
            rbyd = rbyds[i]
            rbyd.redund_blocks = [rbyds[(i+1+j) % len(rbyds)].block
                for j in range(len(rbyds)-1)]
            return rbyd
        else:
            # block may encode a trunk
            block = blocks[0]
            if isinstance(block, tuple):
                if trunk is None:
                    trunk = block[1]
                block = block[0]

        # seek to the block
        f.seek(block * block_size)
        data = f.read(block_size)

        # fetch the rbyd
        rev = fromle32(data[0:4])
        cksum = 0
        cksum_ = crc32c(data[0:4])
        eoff = 0
        j_ = 4
        trunk_ = 0
        trunk__ = 0
        trunk___ = 0
        weight = 0
        weight_ = 0
        weight__ = 0
        wastrunk = False
        trunkeoff = None
        while j_ < len(data) and (not trunk or eoff <= trunk):
            v, tag, w, size, d = fromtag(data[j_:])
            if v != (popc(cksum_) & 1):
                break
            cksum_ = crc32c(data[j_:j_+d], cksum_)
            j_ += d
            if not tag & TAG_ALT and j_ + size > len(data):
                break

            # take care of cksums
            if not tag & TAG_ALT:
                if (tag & 0xff00) != TAG_CKSUM:
                    cksum_ = crc32c(data[j_:j_+size], cksum_)
                # found a cksum?
                else:
                    cksum__ = fromle32(data[j_:j_+4])
                    if cksum_ != cksum__:
                        break
                    # commit what we have
                    eoff = trunkeoff if trunkeoff else j_ + size
                    cksum = cksum_
                    trunk_ = trunk__
                    weight = weight_

            # evaluate trunks
            if (tag & 0xe000) != TAG_CKSUM and (
                    not trunk or trunk >= j_-d or wastrunk):
                # new trunk?
                if not wastrunk:
                    wastrunk = True
                    trunk___ = j_-d
                    weight__ = 0

                # keep track of weight
                weight__ += w

                # end of trunk?
                if not tag & TAG_ALT:
                    wastrunk = False
                    # update trunk/weight unless we found a shrub or an
                    # explicit trunk (which may be a shrub) is requested
                    if not tag & TAG_SHRUB or trunk:
                        trunk__ = trunk___
                        weight_ = weight__
                        # keep track of eoff for best matching trunk
                        if trunk and j_ + size > trunk:
                            trunkeoff = j_ + size

            if not tag & TAG_ALT:
                j_ += size

        return cls(block, data, rev, eoff, trunk_, weight)

    def lookup(self, rid, tag):
        if not self:
            return True, 0, -1, 0, 0, 0, b'', []

        lower = -1
        upper = self.weight
        path = []

        # descend down tree
        j = self.trunk
        while True:
            _, alt, weight_, jump, d = fromtag(self.data[j:])

            # found an alt?
            if alt & TAG_ALT:
                # follow?
                if ((rid, tag & 0xfff) > (upper-weight_-1, alt & 0xfff)
                        if alt & TAG_GT
                        else ((rid, tag & 0xfff)
                            <= (lower+weight_, alt & 0xfff))):
                    lower += upper-lower-1-weight_ if alt & TAG_GT else 0
                    upper -= upper-lower-1-weight_ if not alt & TAG_GT else 0
                    j = j - jump

                    # figure out which color
                    if alt & TAG_R:
                        _, nalt, _, _, _ = fromtag(self.data[j+jump+d:])
                        if nalt & TAG_R:
                            path.append((j+jump, j, True, 'y'))
                        else:
                            path.append((j+jump, j, True, 'r'))
                    else:
                        path.append((j+jump, j, True, 'b'))

                # stay on path
                else:
                    lower += weight_ if not alt & TAG_GT else 0
                    upper -= weight_ if alt & TAG_GT else 0
                    j = j + d

                    # figure out which color
                    if alt & TAG_R:
                        _, nalt, _, _, _ = fromtag(self.data[j:])
                        if nalt & TAG_R:
                            path.append((j-d, j, False, 'y'))
                        else:
                            path.append((j-d, j, False, 'r'))
                    else:
                        path.append((j-d, j, False, 'b'))

            # found tag
            else:
                rid_ = upper-1
                tag_ = alt
                w_ = rid_-lower

                done = not tag_ or (rid_, tag_) < (rid, tag)

                return done, rid_, tag_, w_, j, d, self.data[j+d:j+d+jump], path

    def __bool__(self):
        return bool(self.trunk)

    def __eq__(self, other):
        return self.block == other.block and self.trunk == other.trunk

    def __ne__(self, other):
        return not self.__eq__(other)

    def __iter__(self):
        tag = 0
        rid = -1

        while True:
            done, rid, tag, w, j, d, data, _ = self.lookup(rid, tag+0x1)
            if done:
                break

            yield rid, tag, w, j, d, data

    # btree lookup with this rbyd as the root
    def btree_lookup(self, f, block_size, bid, *,
            depth=None):
        rbyd = self
        rid = bid
        depth_ = 1
        path = []

        # corrupted? return a corrupted block once
        if not rbyd:
            return bid > 0, bid, 0, rbyd, -1, [], path

        while True:
            # collect all tags, normally you don't need to do this
            # but we are debugging here
            name = None
            tags = []
            branch = None
            rid_ = rid
            tag = 0
            w = 0
            for i in it.count():
                done, rid__, tag, w_, j, d, data, _ = rbyd.lookup(
                    rid_, tag+0x1)
                if done or (i != 0 and rid__ != rid_):
                    break

                # first tag indicates the branch's weight
                if i == 0:
                    rid_, w = rid__, w_

                # catch any branches
                if tag == TAG_BTREE:
                    branch = (tag, j, d, data)

                tags.append((tag, j, d, data))

            # keep track of path
            path.append((bid + (rid_-rid), w, rbyd, rid_, tags))

            # descend down branch?
            if branch is not None and (
                    not depth or depth_ < depth):
                tag, j, d, data = branch
                block, trunk, _, cksum = frombtree(data)
                rbyd = Rbyd.fetch(f, block_size, block, trunk)

                # corrupted? bail here so we can keep traversing the tree
                if not rbyd:
                    return False, bid + (rid_-rid), w, rbyd, -1, [], path

                rid -= (rid_-(w-1))
                depth_ += 1
            else:
                return not tags, bid + (rid_-rid), w, rbyd, rid_, tags, path

    # mtree lookup with this rbyd as the mroot
    def mtree_lookup(self, f, block_size, mbid):
        # have mtree?
        done, rid, tag, w, j, d, data, _ = self.lookup(-1, TAG_MTREE)
        if not done and rid == -1 and tag == TAG_MTREE:
            block, trunk, w, cksum = frombtree(data)
            mtree = Rbyd.fetch(f, block_size, block, trunk)
            # corrupted?
            if not mtree:
                return True, -1, 0, None

            # lookup our mbid
            done, mbid, mw, rbyd, rid, tags, path = mtree.btree_lookup(
                f, block_size, mbid)
            if done:
                return True, -1, 0, None

            mdir = next(((tag, j, d, data)
                for tag, j, d, data in tags
                if tag == TAG_MDIR),
                None)
            if not mdir:
                return True, -1, 0, None

            # fetch the mdir
            _, _, _, data = mdir
            blocks = frommdir(data)
            return False, mbid, mw, Rbyd.fetch(f, block_size, blocks)

        else:
            # have mdir?
            done, rid, tag, w, j, _, data, _ = self.lookup(-1, TAG_MDIR)
            if not done and rid == -1 and tag == TAG_MDIR:
                blocks = frommdir(data)
                return False, 0, 0, Rbyd.fetch(f, block_size, blocks)

            else:
                # I guess we're inlined?
                if mbid == -1:
                    return False, -1, 0, self
                else:
                    return True, -1, 0, None

    # lookup by name
    def namelookup(self, did, name):
        # binary search
        best = (False, -1, 0, 0)
        lower = 0
        upper = self.weight
        while lower < upper:
            done, rid, tag, w, j, d, data, _ = self.lookup(
                lower + (upper-1-lower)//2, TAG_NAME)
            if done:
                break

            # treat vestigial names as a catch-all
            if ((tag == TAG_BRANCH and rid-(w-1) == 0)
                    or (tag & 0xff00) != TAG_NAME):
                did_ = 0
                name_ = b''
            else:
                did_, d = fromleb128(data)
                name_ = data[d:]

            # bisect search space
            if (did_, name_) > (did, name):
                upper = rid-(w-1)
            elif (did_, name_) < (did, name):
                lower = rid + 1

                # keep track of best match
                best = (False, rid, tag, w)
            else:
                # found a match
                return True, rid, tag, w

        return best

    # lookup by name with this rbyd as the btree root
    def btree_namelookup(self, f, block_size, did, name):
        rbyd = self
        bid = 0

        while True:
            found, rid, tag, w = rbyd.namelookup(did, name)
            done, rid_, tag_, w_, j, d, data, _ = rbyd.lookup(rid, TAG_STRUCT)

            # found another branch
            if tag_ == TAG_BTREE:
                # update our bid
                bid += rid - (w-1)

                block, trunk, _, cksum = frombtree(data)
                rbyd = Rbyd.fetch(f, block_size, block, trunk)

            # found best match
            else:
                return bid + rid, tag_, w, data

    # lookup by name with this rbyd as the mroot
    def mtree_namelookup(self, f, block_size, did, name):
        # have mtree?
        done, rid, tag, w, j, d, data, _ = self.lookup(-1, TAG_MTREE)
        if not done and rid == -1 and tag == TAG_MTREE:
            block, trunk, w, cksum = frombtree(data)
            mtree = Rbyd.fetch(f, block_size, block, trunk)
            # corrupted?
            if not mtree:
                return False, -1, 0, None, -1, 0, 0

            # lookup our name in the mtree
            mbid, tag_, mw, data = mtree.btree_namelookup(
                f, block_size, did, name)
            if tag_ != TAG_MDIR:
                return False, -1, 0, None, -1, 0, 0

            # fetch the mdir
            blocks = frommdir(data)
            mdir = Rbyd.fetch(f, block_size, blocks)

        else:
            # have mdir?
            done, rid, tag, w, j, _, data, _ = self.lookup(-1, TAG_MDIR)
            if not done and rid == -1 and tag == TAG_MDIR:
                blocks = frommdir(data)
                mbid = 0
                mw = 0
                mdir = Rbyd.fetch(f, block_size, blocks)

            else:
                # I guess we're inlined?
                mbid = -1
                mw = 0
                mdir = self

        # lookup name in our mdir
        found, rid, tag, w = mdir.namelookup(did, name)
        return found, mbid, mw, mdir, rid, tag, w

    # iterate through a directory assuming this is the mtree root
    def mtree_dir(self, f, block_size, did):
        # lookup the bookmark
        found, mbid, mw, mdir, rid, tag, w = self.mtree_namelookup(
            f, block_size, did, b'')
        # iterate through all files until the next bookmark
        while found:
            # lookup each rid
            done, rid, tag, w, j, d, data, _ = mdir.lookup(rid, TAG_NAME)
            if done:
                break

            # parse out each name
            did_, d_ = fromleb128(data)
            name_ = data[d_:]

            # end if we see another did
            if did_ != did:
                break

            # yield what we've found
            yield name_, mbid, mw, mdir, rid, tag, w

            rid += w
            if rid >= mdir.weight:
                rid -= mdir.weight
                mbid += 1

                done, mbid, mw, mdir = self.mtree_lookup(f, block_size, mbid)
                if done:
                    break


# read the config
class Config:
    def __init__(self, mroot=None):
        # read the config from the mroot
        self.config = {}
        if mroot is not None:
            tag = 0
            while True:
                done, rid, tag, w, j, d, data, _ = mroot.lookup(-1, tag+0x1)
                if done or rid != -1 or (tag & 0xff00) != TAG_CONFIG:
                    break

                self.config[tag] = (j+d, data)

    # accessors for known config
    @ft.cached_property
    def magic(self):
        if TAG_MAGIC in self.config:
            _, data = self.config[TAG_MAGIC]
            return data
        else:
            return None

    @ft.cached_property
    def version(self):
        if TAG_VERSION in self.config:
            _, data = self.config[TAG_VERSION]
            d = 0
            major, d_ = fromleb128(data[d:]); d += d_
            minor, d_ = fromleb128(data[d:]); d += d_
            return (major, minor)
        else:
            return (None, None)

    @ft.cached_property
    def flags(self):
        if TAG_FLAGS in self.config:
            _, data = self.config[TAG_FLAGS]
            flags, _ = fromleb128(data)
            return flags
        else:
            return None

    @ft.cached_property
    def cksum_type(self):
        if TAG_CKSUMTYPE in self.config:
            _, data = self.config[TAG_CKSUMTYPE]
            cksum_type, _ = fromleb128(data)
            return cksum_type
        else:
            return None

    @ft.cached_property
    def redund_type(self):
        if TAG_REDUNDTYPE in self.config:
            _, data = self.config[TAG_REDUNDTYPE]
            redund_type, _ = fromleb128(data)
            return redund_type
        else:
            return None

    @ft.cached_property
    def block_limit(self):
        if TAG_BLOCKLIMIT in self.config:
            _, data = self.config[TAG_BLOCKLIMIT]
            block_limit, _ = fromleb128(data)
            return block_limit
        else:
            return None

    @ft.cached_property
    def disk_limit(self):
        if TAG_DISKLIMIT in self.config:
            _, data = self.config[TAG_DISKLIMIT]
            disk_limit, _ = fromleb128(data)
            return disk_limit
        else:
            return None

    @ft.cached_property
    def mleaf_limit(self):
        if TAG_MLEAFLIMIT in self.config:
            _, data = self.config[TAG_MLEAFLIMIT]
            mleaf_limit, _ = fromleb128(data)
            return mleaf_limit
        else:
            return None

    @ft.cached_property
    def size_limit(self):
        if TAG_SIZELIMIT in self.config:
            _, data = self.config[TAG_SIZELIMIT]
            size_limit, _ = fromleb128(data)
            return size_limit
        else:
            return None

    @ft.cached_property
    def name_limit(self):
        if TAG_NAMELIMIT in self.config:
            _, data = self.config[TAG_NAMELIMIT]
            name_limit, _ = fromleb128(data)
            return name_limit
        else:
            return None

    @ft.cached_property
    def utag_limit(self):
        if TAG_UTAGLIMIT in self.config:
            _, data = self.config[TAG_UTAGLIMIT]
            utag_limit, _ = fromleb128(data)
            return utag_limit
        else:
            return None

    @ft.cached_property
    def uattr_limit(self):
        if TAG_UATTRLIMIT in self.config:
            _, data = self.config[TAG_UATTRLIMIT]
            uattr_limit, _ = fromleb128(data)
            return uattr_limit
        else:
            return None

    def repr(self):
        def crepr(tag, data):
            if tag == TAG_MAGIC:
                return 'magic \"%s\"' % ''.join(
                    b if b >= ' ' and b <= '~' else '.'
                    for b in map(chr, self.magic))
            elif tag == TAG_VERSION:
                return 'version v%d.%d' % self.version
            elif tag == TAG_FLAGS:
                return 'flags 0x%x' % self.flags
            elif tag == TAG_CKSUMTYPE:
                return 'cksum_type %d' % self.cksum_type
            elif tag == TAG_REDUNDTYPE:
                return 'redund_type %d' % self.redund_type
            elif tag == TAG_BLOCKLIMIT:
                return 'block_limit %d' % self.block_limit
            elif tag == TAG_DISKLIMIT:
                return 'disk_limit %d' % self.disk_limit
            elif tag == TAG_MLEAFLIMIT:
                return 'mleaf_limit %d' % self.mleaf_limit
            elif tag == TAG_SIZELIMIT:
                return 'size_limit %d' % self.size_limit
            elif tag == TAG_NAMELIMIT:
                return 'name_limit %d' % self.name_limit
            elif tag == TAG_UTAGLIMIT:
                return 'utag_limit %d' % self.utag_limit
            elif tag == TAG_UATTRLIMIT:
                return 'uattr_limit %d' % self.uattr_limit
            else:
                return 'config 0x%02x %d' % (tag, len(data))

        for tag, (j, data) in sorted(self.config.items()):
            yield crepr(tag, data), tag, j, data


# collect gstate
class GState:
    def __init__(self, mleaf_weight):
        self.gstate = {}
        self.gdelta = {}
        self.mleaf_weight = mleaf_weight

    def xor(self, mbid, mw, mdir):
        tag = TAG_GSTATE-0x1
        while True:
            done, rid, tag, w, j, d, data, _ = mdir.lookup(-1, tag+0x1)
            if done or rid != -1 or (tag & 0xff00) != TAG_GSTATE:
                break

            # keep track of gdeltas
            if tag not in self.gdelta:
                self.gdelta[tag] = []
            self.gdelta[tag].append((mbid, mw, mdir, j, d, data))

            # xor gstate
            if tag not in self.gstate:
                self.gstate[tag] = b''
            self.gstate[tag] = bytes(a^b for a,b in it.zip_longest(
                self.gstate[tag], data, fillvalue=0))

    # parsers for some gstate
    @ft.cached_property
    def grm(self):
        if TAG_GRM not in self.gstate:
            return []

        data = self.gstate[TAG_GRM]
        d = 0
        count,  d_ = fromleb128(data[d:]); d += d_
        rms = []
        if count <= 2:
            for _ in range(count):
                mid, d_ = fromleb128(data[d:]); d += d_
                rms.append((
                    mid - (mid % self.mleaf_weight),
                    mid % self.mleaf_weight))
        return rms

    def repr(self):
        def grepr(tag, data):
            if tag == TAG_GRM:
                count, _ = fromleb128(data)
                return 'grm %s' % (
                    'none' if count == 0
                        else ' '.join('%d.%d' % (mbid//self.mleaf_weight, rid)
                                for mbid, rid in self.grm)
                            if count <= 2
                        else '0x%x %d' % (count, len(data)))
            else:
                return 'gstate 0x%02x %d' % (tag, len(data))

        for tag, data in sorted(self.gstate.items()):
            yield grepr(tag, data), tag, data

def frepr(mdir, rid, tag):
    if tag == TAG_BOOKMARK:
        # read the did
        did = '?'
        done, rid_, tag_, w_, j, d, data, _ = mdir.lookup(rid, tag)
        if not done and rid_ == rid and tag_ == tag:
            did, _ = fromleb128(data)
            did = '0x%x' % did
        return 'bookmark %s' % did

    elif tag == TAG_DIR:
        # read the did
        did = '?'
        done, rid_, tag_, w_, j, d, data, _ = mdir.lookup(rid, TAG_DID)
        if not done and rid_ == rid and tag_ == TAG_DID:
            did, _ = fromleb128(data)
            did = '0x%x' % did
        return 'dir %s' % did

    elif tag == TAG_REG:
        size = 0
        structs = []
        # inlined?
        done, rid_, tag_, w_, j, d, data, _ = mdir.lookup(rid, TAG_INLINED)
        if not done and rid_ == rid and tag_ == TAG_INLINED:
            size = max(size, len(data))
            structs.append('inlined 0x%x.%x %d' % (mdir.block, j+d, len(data)))
        # inlined tree?
        done, rid_, tag_, w_, j, d, data, _ = mdir.lookup(rid, TAG_TRUNK)
        if not done and rid_ == rid and tag_ == TAG_TRUNK:
            d = 0
            trunk, d_ = fromleb128(data[d:]); d += d_
            weight, d_ = fromleb128(data[d:]); d += d_
            size = max(size, weight)
            structs.append('trunk 0x%x.%x' % (mdir.block, trunk))
        return 'reg %s' % ', '.join(it.chain(['%d' % size], structs))

    else:
        return 'type 0x%02x' % (tag & 0xff)


def main(disk, mroots=None, *,
        block_size=None,
        mleaf_weight=None,
        color='auto',
        **args):
    # figure out what color should be
    if color == 'auto':
        color = sys.stdout.isatty()
    elif color == 'always':
        color = True
    else:
        color = False

    # flatten mroots, default to 0x{0,1}
    if not mroots:
        mroots = [[0,1]]
    mroots = [block for mroots_ in mroots for block in mroots_]

    # we seek around a bunch, so just keep the disk open
    with open(disk, 'rb') as f:
        # if block_size is omitted, assume the block device is one big block
        if block_size is None:
            f.seek(0, os.SEEK_END)
            block_size = f.tell()

        # determine the mleaf_weight from the block_size, this is just for
        # printing purposes
        if mleaf_weight is None:
            mleaf_weight = 1 << m.ceil(m.log2(block_size // 16))

        # before we print, we need to do a pass for a few things:
        # - find the actual mroot
        # - find the total weight
        # - are we corrupted?
        # - collect config
        # - collect gstate
        # - any missing or orphaned bookmark entries
        bweight = 0
        rweight = 0
        corrupted = False
        gstate = GState(mleaf_weight)
        config = Config()
        dir_dids = [(0, b'', -1, 0, None, -1, TAG_DID, 0)]
        bookmark_dids = []

        mroot = Rbyd.fetch(f, block_size, mroots)
        mdepth = 1
        while True:
            # corrupted?
            if not mroot:
                corrupted = True
                break

            rweight = max(rweight, mroot.weight)
            # yes we get gstate from all mroots
            gstate.xor(-1, 0, mroot)
            # get the config
            config = Config(mroot)

            # find any dids
            for rid, tag, w, j, d, data in mroot:
                if tag == TAG_DID:
                    did, d = fromleb128(data)
                    dir_dids.append(
                        (did, data[d:], -1, 0, mroot, rid, tag, w))
                elif tag == TAG_BOOKMARK:
                    did, d = fromleb128(data)
                    bookmark_dids.append(
                        (did, data[d:], -1, 0, mroot, rid, tag, w))

            # fetch the next mroot
            done, rid, tag, w, j, d, data, _ = mroot.lookup(-1, TAG_MROOT)
            if not (not done and rid == -1 and tag == TAG_MROOT):
                break

            blocks = frommdir(data)
            mroot = Rbyd.fetch(f, block_size, blocks)
            mdepth += 1

        # fetch the mdir, if there is one
        mdir = None
        done, rid, tag, w, j, _, data, _ = mroot.lookup(-1, TAG_MDIR)
        if not done and rid == -1 and tag == TAG_MDIR:
            blocks = frommdir(data)
            mdir = Rbyd.fetch(f, block_size, blocks)

            # corrupted?
            if not mdir:
                corrupted = True
            else:
                rweight = max(rweight, mdir.weight)
                gstate.xor(0, mdir)

                # find any dids
                for rid, tag, w, j, d, data in mdir:
                    if tag == TAG_DID:
                        did, d = fromleb128(data)
                        dir_dids.append((
                            did, data[d:], 0, 0, mdir, rid, tag, w))
                    elif tag == TAG_BOOKMARK:
                        did, d = fromleb128(data)
                        bookmark_dids.append((
                            did, data[d:], 0, 0, mdir, rid, tag, w))

        # fetch the actual mtree, if there is one
        mtree = None
        done, rid, tag, w, j, d, data, _ = mroot.lookup(-1, TAG_MTREE)
        if not done and rid == -1 and tag == TAG_MTREE:
            block, trunk, w, cksum = frombtree(data)
            mtree = Rbyd.fetch(f, block_size, block, trunk)

            bweight = w

            # traverse entries
            mbid = -1
            while True:
                done, mbid, mw, rbyd, rid, tags, path = mtree.btree_lookup(
                    f, block_size, mbid+1)
                if done:
                    break

                # corrupted?
                if not rbyd:
                    corrupted = True
                    continue

                mdir__ = next(((tag, j, d, data)
                    for tag, j, d, data in tags
                    if tag == TAG_MDIR),
                    None)

                if mdir__:
                    # fetch the mdir
                    _, _, _, data = mdir__
                    blocks = frommdir(data)
                    mdir_ = Rbyd.fetch(f, block_size, blocks)

                    # corrupted?
                    if not mdir_:
                        corrupted = True
                    else:
                        rweight = max(rweight, mdir_.weight)
                        gstate.xor(mbid, mw, mdir_)

                        # find any dids
                        for rid, tag, w, j, d, data in mdir_:
                            if tag == TAG_DID:
                                did, d = fromleb128(data)
                                dir_dids.append((
                                    did, data[d:],
                                    mbid, mw, mdir_, rid, tag, w))
                            elif tag == TAG_BOOKMARK:
                                did, d = fromleb128(data)
                                bookmark_dids.append((
                                    did, data[d:],
                                    mbid, mw, mdir_, rid, tag, w))

        # remove grms from our found dids, we treat these as already deleted
        grmed_dir_dids = {did_
            for (did_, name_, mbid_, mw_, mdir_, rid_, tag_, w_)
            in dir_dids
            if (max(mbid_-max(mw_-1, 0), 0), rid_) not in gstate.grm}
        grmed_bookmark_dids = {did_
            for (did_, name_, mbid_, mw_, mdir_, rid_, tag_, w_)
            in bookmark_dids
            if (max(mbid_-max(mw_-1, 0), 0), rid_) not in gstate.grm}

        # treat the filesystem as corrupted if our dirs and bookmarks are
        # mismatched, this should never happen unless there's a bug
        if grmed_dir_dids != grmed_bookmark_dids:
            corrupted = True

        # are we going to end up rendering the dtree?
        dtree = args.get('dtree') or not (
            args.get('config') or args.get('gstate'))

        # do a pass to find the width that fits file names+tree, this
        # may not terminate! It's up to the user to use -Z in that case
        f_width = 0
        if dtree:
            def rec_f_width(did, depth):
                depth_ = 0
                width_ = 0
                for name, mbid, mw, mdir, rid, tag, w in mroot.mtree_dir(
                        f, block_size, did):
                    width_ = max(width_, len(name))
                    # recurse?
                    if tag == TAG_DIR and depth > 1:
                        done, rid_, tag_, w_, j, d, data, _ = mdir.lookup(
                            rid, TAG_DID)
                        if not done and rid_ == rid and tag_ == TAG_DID:
                            did_, _ = fromleb128(data)
                            depth__, width__ = rec_f_width(did_, depth-1)
                            depth_ = max(depth_, depth__)
                            width_ = max(width_, width__)
                return 1+depth_, width_

            depth, f_width = rec_f_width(0, args.get('depth') or m.inf)
            # adjust to make space for max depth
            f_width += 4*(depth-1)


        #### actual debugging begins here

        # print some information about the filesystem
        print('littlefs v%s.%s %s, rev %d, weight %d.%d' % (
            config.version[0] if config.version[0] is not None else '?',
            config.version[1] if config.version[1] is not None else '?',
            mroot.addr(), mroot.rev, bweight//mleaf_weight, 1*mleaf_weight))

        # dynamically size the id field
        w_width = (m.ceil(m.log10(max(1, bweight//mleaf_weight)+1))
            + 2*m.ceil(m.log10(max(1, rweight)+1))
            + 2)

        # print config?
        if args.get('config'):
            for i, (repr_, tag, j, data) in enumerate(config.repr()):
                print('%12s %-*s  %s' % (
                    'config:' if i == 0 else '',
                    w_width + 23, repr_,
                    next(xxd(data, 8), '')
                        if not args.get('no_truncate') else ''))

                # show in-device representation
                if args.get('device'):
                    print('%11s  %*s %s' % (
                        '',
                        w_width, '',
                        '%-22s%s' % (
                            '%04x %08x %07x' % (tag, 0, len(data)),
                            '  %s' % ' '.join(
                                    '%08x' % fromle32(
                                        data[i*4 : min(i*4+4,len(data))])
                                    for i in range(
                                        min(m.ceil(len(data)/4),
                                        3)))[:23]
                                if not args.get('no_truncate') else '')))

                # show on-disk encoding
                if args.get('raw') or args.get('no_truncate'):
                    for o, line in enumerate(xxd(data)):
                        print('%11s: %*s %s' % (
                            '%04x' % (j + o*16),
                            w_width, '',
                            line))

        # print gstate?
        if args.get('gstate'):
            for i, (repr_, tag, data) in enumerate(gstate.repr()):
                print('%12s %-*s  %s' % (
                    'gstate:' if i == 0 else '',
                    w_width + 23, repr_,
                    next(xxd(data, 8), '')
                        if not args.get('no_truncate') else ''))

                # show in-device representation
                if args.get('device'):
                    print('%11s  %*s %s' % (
                        '',
                        w_width, '',
                        '%-22s%s' % (
                            '',
                            '  %s' % ' '.join(
                                    '%08x' % fromle32(
                                        data[i*4 : min(i*4+4,len(data))])
                                    for i in range(
                                        min(m.ceil(len(data)/4),
                                        3)))[:23]
                                if not args.get('no_truncate') else '')))

                # show on-disk encoding
                if args.get('raw') or args.get('no_truncate'):
                    for o, line in enumerate(xxd(data)):
                        print('%11s: %*s %s' % (
                            '%04x' % (o*16),
                            w_width, '',
                            line))

                # print gdeltas?
                if args.get('gdelta'):
                    for mbid, mw, mdir, j, d, data in gstate.gdelta[tag]:
                        print('%s{%s}: %*s %-22s  %s%s' % (
                            '\x1b[90m' if color else '',
                            ','.join('%04x' % block
                                for block in it.chain([mdir.block],
                                    mdir.redund_blocks)),
                            w_width, mbid//mleaf_weight,
                            tagrepr(tag, 0, len(data)),
                            next(xxd(data, 8), '')
                                if not args.get('no_truncate') else '',
                            '\x1b[m' if color else ''))

                        # show in-device representation
                        if args.get('device'):
                            print('%11s  %*s %s' % (
                                '',
                                w_width, '',
                                '%-22s%s' % (
                                    '%04x %08x %07x' % (tag, 0, len(data)),
                                    '  %s' % ' '.join(
                                            '%08x' % fromle32(
                                                data[i*4
                                                    : min(i*4+4,len(data))])
                                            for i in range(
                                                min(m.ceil(len(data)/4),
                                                3)))[:23]
                                        if not args.get('no_truncate')
                                            else '')))

                        # show on-disk encoding
                        if args.get('raw'):
                            for o, line in enumerate(xxd(mdir.data[j:j+d])):
                                print('%11s: %*s %s' % (
                                    '%04x' % (j + o*16),
                                    w_width, '',
                                    line))
                        if args.get('raw') or args.get('no_truncate'):
                            for o, line in enumerate(xxd(data)):
                                print('%11s: %*s %s' % (
                                    '%04x' % (j+d + o*16),
                                    w_width, '',
                                    line))

        # print dtree?
        if dtree:
            # only show mdir on change
            pmbid = None
            # recursively print directories
            def rec_dir(did, depth, prefixes=('', '', '', '')):
                nonlocal pmbid
                # collect all entries first so we know when the dir ends
                dir = []
                for name, mbid, mw, mdir, rid, tag, w in mroot.mtree_dir(
                        f, block_size, did):
                    if not args.get('all'):
                        # skip bookmarks
                        if tag == TAG_BOOKMARK:
                            continue
                        # skip grmed entries
                        if (max(mbid-max(mw-1, 0), 0), rid) in gstate.grm:
                            continue
                    dir.append((name, mbid, mw, mdir, rid, tag, w))

                # if we're root, append any orphaned bookmark entries so they
                # get reported
                if did == 0:
                    for did, name, mbid, mw, mdir, rid, tag, w in bookmark_dids:
                        if did in grmed_dir_dids:
                            continue
                        # skip grmed entries
                        if (not args.get('all')
                                and (max(mbid-max(mw-1, 0), 0), rid)
                                    in gstate.grm):
                            continue
                        dir.append((name, mbid, mw, mdir, rid, tag, w))

                for i, (name, mbid, mw, mdir, rid, tag, w) in enumerate(dir):
                    # some special situations worth reporting
                    notes = []
                    grmed = (max(mbid-max(mw-1, 0), 0), rid) in gstate.grm
                    # grmed?
                    if grmed:
                        notes.append('grmed')
                    # missing bookmark?
                    if tag == TAG_DIR:
                        done, rid_, tag_, w_, j, d, data, _ = mdir.lookup(
                            rid, TAG_DID)
                        if not done and rid_ == rid and tag_ == TAG_DID:
                            did_, _ = fromleb128(data)
                            if did_ not in grmed_bookmark_dids:
                                notes.append('missing bookmark')
                    # orphaned?
                    if tag == TAG_BOOKMARK:
                        done, rid_, tag_, w_, j, d, data, _ = mdir.lookup(
                            rid, tag)
                        if not done and rid_ == rid and tag_ == tag:
                            did_, _ = fromleb128(data)
                            if did_ not in grmed_dir_dids:
                                notes.append('orphaned')

                    # print human readable dtree entry
                    print('%s%12s %*s %-*s  %s%s%s' % (
                        '\x1b[90m' if color and (grmed or tag == TAG_BOOKMARK)
                            else '',
                        '{%s}:' % ','.join('%04x' % block
                            for block in it.chain([mdir.block],
                                mdir.redund_blocks))
                            if mbid != pmbid else '',
                        w_width, '%d.%d-%d' % (
                                mbid//mleaf_weight, rid-(w-1), rid)
                            if w > 1 else '%d.%d' % (mbid//mleaf_weight, rid)
                            if w > 0 else '',
                        f_width, '%s%s' % (
                            prefixes[0+(i==len(dir)-1)],
                            name.decode('utf8')),
                        frepr(mdir, rid, tag),
                        ' %s(%s)%s' % (
                            '\x1b[31m' if color and not grmed else '',
                            ', '.join(notes),
                            '\x1b[m' if color and not grmed else '')
                            if notes else '',
                        '\x1b[m' if color and (grmed or tag == TAG_BOOKMARK)
                            else ''))
                    pmbid = mbid

                    # print attrs associated with this file?
                    if args.get('attrs'):
                        tag_ = 0
                        while True:
                            done, rid_, tag_, w_, j, d, data, _ = mdir.lookup(
                                rid, tag_+0x1)
                            if done or rid_ != rid:
                                break

                            print('%12s %*s %-22s  %s' % (
                                '',
                                w_width, '',
                                tagrepr(tag_, w_, len(data)),
                                next(xxd(data, 8), '')
                                    if not args.get('no_truncate') else ''))

                            # show in-device representation
                            if args.get('device'):
                                print('%11s  %*s %s' % (
                                    '',
                                    w_width, '',
                                    '%-22s%s' % (
                                        '%04x %08x %07x' % (
                                            tag_, w_, len(data)),
                                        '  %s' % ' '.join(
                                                '%08x' % fromle32(
                                                    data[i*4
                                                        : min(i*4+4,len(data))])
                                                for i in range(
                                                    min(m.ceil(len(data)/4),
                                                    3)))[:23]
                                            if not args.get('no_truncate')
                                                else '')))

                            # show on-disk encoding
                            if args.get('raw'):
                                for o, line in enumerate(xxd(mdir.data[j:j+d])):
                                    print('%11s: %*s %s' % (
                                        '%04x' % (j + o*16),
                                        w_width, '',
                                        line))
                            if args.get('raw') or args.get('no_truncate'):
                                for o, line in enumerate(xxd(data)):
                                    print('%11s: %*s %s' % (
                                        '%04x' % (j+d + o*16),
                                        w_width, '',
                                        line))

                    # recurse?
                    if tag == TAG_DIR and depth > 1:
                        done, rid_, tag_, w_, j, d, data, _ = mdir.lookup(
                            rid, TAG_DID)
                        if not done and rid_ == rid and tag_ == TAG_DID:
                            did_, _ = fromleb128(data)
                            rec_dir(
                                did_,
                                depth-1,
                                (prefixes[2+(i==len(dir)-1)] + "|-> ",
                                 prefixes[2+(i==len(dir)-1)] + "'-> ",
                                 prefixes[2+(i==len(dir)-1)] + "|   ",
                                 prefixes[2+(i==len(dir)-1)] + "    "))

            rec_dir(0, args.get('depth') or m.inf)

        if args.get('error_on_corrupt') and corrupted:
            sys.exit(2)


if __name__ == "__main__":
    import argparse
    import sys
    parser = argparse.ArgumentParser(
        description="Debug littlefs's metadata tree.",
        allow_abbrev=False)
    parser.add_argument(
        'disk',
        help="File containing the block device.")
    parser.add_argument(
        'mroots',
        nargs='*',
        type=rbydaddr,
        help="Block address of the mroots. Defaults to 0x{0,1}.")
    parser.add_argument(
        '-B', '--block-size',
        type=lambda x: int(x, 0),
        help="Block size in bytes.")
    parser.add_argument(
        '-M', '--mleaf-weight',
        type=lambda x: int(x, 0),
        help="Maximum weight of mdirs for mid decoding. Defaults to a "
            "block_size derived value.")
    parser.add_argument(
        '--color',
        choices=['never', 'always', 'auto'],
        default='auto',
        help="When to use terminal colors. Defaults to 'auto'.")
    parser.add_argument(
        '-c', '--config',
        action='store_true',
        help="Show the on-disk config.")
    parser.add_argument(
        '-g', '--gstate',
        action='store_true',
        help="Show the current global-state.")
    parser.add_argument(
        '-d', '--gdelta',
        action='store_true',
        help="Show the gdelta that xors into the global-state.")
    parser.add_argument(
        '-t', '--dtree', '--tree',
        action='store_true',
        help="Show the directory tree (default).")
    parser.add_argument(
        '-A', '--attrs',
        action='store_true',
        help="Show all attributes belonging to each file.")
    parser.add_argument(
        '-a', '--all',
        action='store_true',
        help="Show all files including bookmarks and grmed files.")
    parser.add_argument(
        '-r', '--raw',
        action='store_true',
        help="Show the raw data including tag encodings.")
    parser.add_argument(
        '-x', '--device',
        action='store_true',
        help="Show the device-side representation of tags.")
    parser.add_argument(
        '-T', '--no-truncate',
        action='store_true',
        help="Don't truncate, show the full contents.")
    parser.add_argument(
        '-Z', '--depth',
        nargs='?',
        type=lambda x: int(x, 0),
        const=0,
        help="Depth of the filesystem tree to show.")
    parser.add_argument(
        '-e', '--error-on-corrupt',
        action='store_true',
        help="Error if B-tree is corrupt.")
    sys.exit(main(**{k: v
        for k, v in vars(parser.parse_intermixed_args()).items()
        if v is not None}))
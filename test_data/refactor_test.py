#! /usr/bin/env pysh
#-*-python-*-

"""This module runs the refactoring code on a sequence of reference
files in order to test automatic rmap refactoring.  Based on the
reference file and a given context, this code determines which rmap to
modify and attempts to add the new reference file to it.

When --replace is specified on the command line, this code expects
that the given references are already in the rmaps and should replace
the originals when re-inserted.   This changes the expected actions from
"insert" to "replace" and defines what looks interesting.
"""

import sys
import random
import shutil
import os.path

from crds import (rmap, log, refactor, pysh, matches, utils, selectors)
import crds.client as client

def newfile(fname):
   root, ext = os.path.splitext(fname)
   return "./" + os.path.basename(root) + "_new" + ext

def new_references(new_file):
    for line in open(new_file):
        if not line.strip():
            continue
        new_reference = line.split()[0]
        yield new_reference

def separator(char="-", len=80):
    log.write(char*len)        

def main(context, new_references, expected_action_type):
    """Insert `new_references` into `context`, outputting debug information
    when the insertion doesn't result in the expected action.   For files already
    in `context`,  the expected action is a replacement.   For files not in
    `context`,  the expected action is an insertion.   Here "in" refers to
    """
    for reference in new_references:
        
        pmap = rmap.get_cached_mapping(context)

        try:
           refpath = pmap.locate.locate_server_reference(reference)
        except KeyError:
           log.error("Can't locate reference file", repr(reference))
           continue

        try:
            instrument, filekind, old_rmap_path = get_corresponding_rmap(context, refpath)
        except Exception, exc:
            log.error("Failed getting corresponding rmap for", repr(reference), repr(str(exc)))
            continue

        new_rmap_path = "./temp.rmap"
            
        new_refpath = newfile(refpath)      # a different looking file to insert
        pysh.sh("ln -s ${refpath} ${new_refpath}")
        
        try:
            do_refactoring(context, new_rmap_path, old_rmap_path, new_refpath, refpath, 0, expected_action_type)
        except Exception, exc:
            log.error("Exception", str(exc))
        
        pysh.sh("rm -f ${new_rmap_path} ${new_refpath}")

    sys.stdout.flush()
    sys.stderr.flush()
    log.write()
    separator("=")
    log.standard_status()

def do_refactoring(context, new_rmap_path, old_rmap_path, new_refpath, old_refpath, verbosity=0,
                   expected_action_type="insert"):

    separator("=")
    log.info("Reference", os.path.basename(old_rmap_path), old_refpath)

    pysh.sh("rm -f ${new_rmap_path}")
    actions = refactor.rmap_insert_references(old_rmap_path, new_rmap_path, [new_refpath])

    as_expected = True
    if expected_action_type == "replace":
         expected_matches = matches.find_match_tuples(context, os.path.basename(old_refpath))    
         log.info("Expected matches:", expected_matches)
         for action in actions:
             log.info(action)
             if action.action != "replace":
                 log.warning("Unexpected action:", action.action.upper())
                 as_expected = False
             for expected in expected_matches:
                 if selectors.match_equivalent(action.rmap_match_tuple, expected):
                     break
             else:
                 if action.action != "replace":
                     log.info("New match at", action.rmap_match_tuple)
                     as_expected = False
         for expected in expected_matches:
             for action in actions:
                 if selectors.match_equivalent(action.rmap_match_tuple, expected):
                     break
             else:
                 try:
                     instrument, filekind = utils.get_file_properties("hst", new_refpath)
                 except Exception:
                     instrument, filekind = "UNKNOWN", "UNKNOWN"
                 log.error("Missing expected match for", repr((instrument, filekind)), 
                           "at", expected)
                 as_expected = False    
    else:
        for action in actions:
            if action.action != "insert":
                log.warning("Unexpected action:", action)
                as_expected = False
            else:
                log.info(action)
        if not actions:
            expected_matches = matches.find_match_tuples(context, os.path.basename(new_refpath))    
            log.warning("No actions for", new_refpath, "matches", expected_matches)
            as_expected = False

    if not as_expected or verbosity:
        pysh.sh("rm -f ${new_rmap_path}")
        actions = refactor.rmap_insert_references(old_rmap_path, new_rmap_path, [new_refpath])
        separator()
        log.write("diffing", repr(new_rmap_path), "from", repr(old_rmap_path))
        sys.stdout.flush()
        sys.stderr.flush()
        pysh.sh("diff -c ${old_rmap_path} ${new_rmap_path}")
        sys.stdout.flush()
        sys.stderr.flush()
        separator()
        pysh.sh("cd ../../hst_gentools; python db_test.py info ${old_refpath}")
 
def get_corresponding_rmap(context, refpath):
    """Return the path to the rmap which *would* refer to `reference` in `context.`
    """
    pmap = rmap.get_cached_mapping(context)
    instrument, filekind = utils.get_file_properties(pmap.observatory, refpath)
    old_rmap = rmap.locate_mapping(pmap.get_imap(instrument).get_rmap(filekind).name)
    return instrument, filekind, old_rmap

if __name__ == "__main__":

    if "--replace" in sys.argv:
       sys.argv.remove("--replace")
       expected_action_type = "replace"
    else:
       expected_action_type = "insert"
       
    if "--verbose" in sys.argv:
        sys.argv.remove("--verbose")
        log.set_verbose()

    if len(sys.argv) < 3:
        log.write("usage: %s  [--verbose] [--replace] <context>  @file_list | <reference_file>..." % sys.argv[0])
        sys.exit(-1)
    if sys.argv[2].startswith("@"):
        references = new_references(sys.argv[2][1:])
    else:
        references = sys.argv[2:]

    context = sys.argv[1]
    assert rmap.is_mapping(context), "First parameter should be a .pmap"

    import cProfile
    cProfile.runctx('main(context, references, expected_action_type)', globals(), locals(), "refactor.stats")

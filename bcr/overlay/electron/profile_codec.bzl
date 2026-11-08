"""Expand shared string lists in generated native profiles."""

def _expand(value, pool, pending):
    if type(value) == "dict" and "_strings" in value:
        if value.keys() != ["_strings"] or type(value["_strings"]) != "list":
            fail("Invalid native profile string reference")
        for index in value["_strings"]:
            if type(index) != "int" or index < 0 or index >= len(pool):
                fail("Invalid native profile string index")
        return [pool[index] for index in value["_strings"]]
    if type(value) in ["dict", "list"]:
        pending.append(value)
    return value

def unpack_profile(profile):
    if "_string_pool" not in profile:
        return profile
    pool = profile.pop("_string_pool")
    if type(pool) != "list" or any([type(item) != "string" for item in pool]):
        fail("Invalid native profile string pool")
    pending = [profile]
    for _ in range(32):
        current = pending
        pending = []
        for node in current:
            if type(node) == "dict":
                for key, value in node.items():
                    node[key] = _expand(value, pool, pending)
            else:
                for index in range(len(node)):
                    node[index] = _expand(node[index], pool, pending)
        if not pending:
            return profile
    fail("Native profile nesting exceeds limit")

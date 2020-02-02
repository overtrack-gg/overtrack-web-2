def ifnone(v, o):
    if v is None:
        return o
    else:
        return v


filters = {
    'ifnone': ifnone
}

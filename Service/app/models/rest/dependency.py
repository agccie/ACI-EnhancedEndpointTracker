class RestDependency(object):
    """ object dependency tree """

    def __init__(self, obj, path=None):
        self.obj = obj
        if self.obj is not None:
            self.classname = self.obj.__name__.lower()
        else:
            self.classname = None
        self.path = path
        self.parent = None
        self.parent_classname = None
        self.children = []
        self.loose = []  # list of children with missing parents

    def __repr__(self):
        # get string representation of dependency tree
        if self.classname is None:
            lines = ["root"]
        else:
            lines = ["%s (parent: %s)" % (self.classname, self.parent_classname)]
        for c in self.children:
            for l in ("%s" % c).split("\n"):
                lines.append("  %s" % l)
        if len(self.loose) > 0:
            lines.append("**loose:")
            for c in self.loose:
                for l in ("%s" % c).split("\n"):
                    lines.append("    %s" % l)
        return "\n".join(lines)

    def set_parent_classname(self, parent):
        """ set pointer for parent classname """
        self.parent_classname = ("%s" % parent).lower()

    def add_loose(self, node):
        """ add node to loose list """
        assert isinstance(node, RestDependency)
        if node not in self.loose:
            self.loose.append(node)

    def add_child(self, node):
        """ add node to children list """
        assert isinstance(node, RestDependency)
        if node not in self.children:
            self.children.append(node)
        if node.parent is None:
            node.parent = self

    def remove_child(self, node):
        """ remove node from children list """
        assert isinstance(node, RestDependency)
        if node in self.children:
            self.children.remove(node)
            node.parent = None

    def find_classname(self, classname):
        """ walk children to find node holding corresponding Rest obj
            return None if not found
        """
        if self.classname == classname:
            return self
        for c in self.children:
            r = c.find_classname(classname)
            if r is not None:
                return r
        # possible that parent is in loose nodes
        for c in self.loose:
            r = c.find_classname(classname)
            if r is not None:
                return r
        return None

    def build(self):
        """ once all children/loose nodes are added, build full tree 
            note, there's no guarantee for order of nodes within children or
            loose array, therefore each need to be checked for possible parent
        """
        while len(self.loose) > 0:
            node = self.loose.pop()
            parent = self.find_classname(node.parent_classname)
            if parent is not None:
                parent.add_child(node)
            else:
                msg = "Rest dependency mapping failed. "
                msg += "Unable to map parent '%s' to class '%s'" % (
                    node.parent_classname, node.classname)
                raise Exception(msg)

    def get_ordered_objects(self):
        """ walk tree and return ordered list with parent nodes always before
            children nodes
        """
        objs = []
        if self.obj is not None:
            objs.append(self)
        # sort children nodes for deterministic ordering
        for c in sorted(self.children, key=lambda c: c.classname):
            ch = c.get_ordered_objects()
            objs += ch
        return objs

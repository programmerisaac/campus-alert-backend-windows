import os

def print_tree(startpath, prefix="", root_static_path=None):
    files = sorted(os.listdir(startpath))

    filtered = []
    for f in files:
        path = os.path.join(startpath, f)

        # Skip __pycache__ and .git everywhere
        if f in ("__pycache__", ".git"):
            continue

        # Skip the root-level static folder
        if root_static_path and os.path.abspath(path) == root_static_path:
            continue

        # Skip anything inside the static folder
        if root_static_path and os.path.abspath(path).startswith(root_static_path):
            continue

        filtered.append(f)

    for index, name in enumerate(filtered):
        path = os.path.join(startpath, name)
        connector = "└── " if index == len(filtered) - 1 else "├── "
        print(prefix + connector + name)

        if os.path.isdir(path):
            extension = "    " if index == len(filtered) - 1 else "│   "
            print_tree(path, prefix + extension, root_static_path)


if __name__ == "__main__":
    cwd = os.getcwd()
    root_dir = os.path.basename(cwd)

    # Define the absolute path to the root-level static folder
    static_path = os.path.abspath(os.path.join(cwd, "static"))

    print(root_dir + "/")
    print_tree(".", root_static_path=static_path)



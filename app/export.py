import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "semprini.settings.dev")
django.setup()


def main():
    from puput.models import EntryPage, BlogPage

    blog = BlogPage.objects.get(title="Semprini")

    for entry in blog.get_entries():
        export = "<!doctype html>\n<html>\n    <head>\n"
        export += f"        <title>{entry.title}</title>\n"
        export += f'        <meta name="author" content="{entry.owner}" />\n'
        export += "    </head>\n    <body>\n"
        export += f"        <h1>{entry.title}</h1>\n"
        export += entry.body
        export += "\n    </body\n</html>"

        print(entry.title)
        with open(f"./export/{entry.id}.html","w", encoding="utf-8") as f:
            f.writelines( export )


if __name__ == '__main__':
    main()

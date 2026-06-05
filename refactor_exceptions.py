import glob
import os


def refactor_exceptions():
    scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
    files = glob.glob(f"{scripts_dir}/**/*.py", recursive=True)

    count = 0
    for f in files:
        with open(f) as file:
            content = file.read()

        if "except Exception:" in content:
            new_content = content.replace("except Exception:", "except Exception as e:")
            with open(f, "w") as file:
                file.write(new_content)
            count += 1
            print(f"Refactored {f}")

    print(f"Total files refactored: {count}")


if __name__ == "__main__":
    refactor_exceptions()

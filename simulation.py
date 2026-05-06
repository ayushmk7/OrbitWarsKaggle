from kaggle_environments import make
import os
import webbrowser
from agent import all_in

# CREATING HTML FILE

env = make("orbit_wars")
print("hello")
env.run([all_in, "random"])

html = env.render(mode="html")

with open("orbit_wars.html", "w") as f:
    f.write(html)

print("Saved to orbit_wars.html")
# Classes

## Artifact

Creates a list of all the available Artifacts. Has subclasses for each LCO version. Have a look at it new LCO versions can be easily added.

Sample workflow to create a json with the available Artifacts of LCO 5.4.5:

```python3
art545 = Artifact545()
art545.create_dir()     # get all available Artifacts
art545.cleanup_dir()    # cleans the directory structure so that only valid Artifacts are in it
art545.dump_dir()       # dumps the available Artifacts into a json to cache them can be loaded with art545.load_dir()
art545.create_list()    # gets data from inside the Artifacts like PVER, name ...
art545.cleanup_list()   # cleans the list so that only valid Artifacts are in it
art545.dump_list()      # dumps the list into a json to cache them can be loaded with art545.load_list()
```

## Check

Finds the correct Artifacts from the created `.dump_list()` to create an json which is used to upload.

```python3
Check.transform_excel("missing.xlsx", "missing.csv")    # transform the xlsx so that the Check class can work with it
check = Check(["545list.json"], "missing.csv")          # (.dump_list(), missing.csv)
check.compare()                                         # creates the mapping
check.dump()                                            # dumps the mapping
# now please check per hand and also fix issues which cant be resolved automatically (two possible PVER for one Artifact etc.)
Check.create_mig("check.json")                          # creates out of the .dump() json a json which then can be used to upload the data
```
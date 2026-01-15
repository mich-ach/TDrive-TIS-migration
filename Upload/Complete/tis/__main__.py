from Artifacts import *
from Check import *

if __name__ == '__main__':
    art545 = Artifact545()
    art545.create_dir()
    art545.cleanup_dir()
    art545.dump_dir()
    art545.create_list()
    art545.cleanup_list()
    art545.dump_list()

    art5411 = Artifact5411()
    art5411.create_dir()
    art5411.cleanup_dir()
    art5411.dump_dir()
    art5411.create_list()
    art5411.cleanup_list()
    art5411.dump_list()

    Check.transform_excel("missing.xlsx", "missing.csv")
    check = Check(["545list.json", "5411list.json"], "missing.csv")
    check.compare()
    check.dump()
    Check.create_mig("check.json")
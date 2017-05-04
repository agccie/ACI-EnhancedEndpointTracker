"""
ACI app packager script that takes current build and maps to appropriate
aci_app format.  Also, removes unnecssary files for App-store app and performs
fixups for a few static files
"""

import argparse, sys, os, logging, subprocess, re
logger = logging.getLogger(__name__)

def getargs():

    # set default app_base_dir to eptracker directory
    dir_path = os.path.dirname(os.path.realpath(__file__))
    dir_path = re.sub("aci_app_store$", "", dir_path)

    # return user arguments
    desc = """
    Package appstore content into aci app
    """
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("--debug", action="store", help="debug level",
        choices=["debug","info","warn","error","critical"])

    parser.add_argument("--appId", action="store", dest="appId",
        default="EnhancedEndpointTracker",
        help="project name (appId)")
    parser.add_argument("--vendor", action="store", dest="vendor",
        default="Cisco", help="Vendor domain")
    parser.add_argument("--src", action="store", dest="src", 
        default=dir_path, help="source code git url or directory")
    parser.add_argument("--img", action="store", dest="img", 
        default="agccie/ept:latest",
        help="docker image name or path to .tgz file")
    parser.add_argument("--key", action="store", dest="key", default=None,
        help="private key used to sign application")

    args = parser.parse_args()

    # configure logging
    logger.setLevel({
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warn": logging.WARNING,
        "error": logging.ERROR,
        "critical": logging.CRITICAL
    }.get(args.debug, logging.INFO))
    logger_handler = logging.StreamHandler(sys.stdout)
    fmt ="%(asctime)s.%(msecs).03d %(levelname)8s %(filename)"
    fmt+="16s:(%(lineno)d): %(message)s"
    logger_handler.setFormatter(logging.Formatter(
        fmt=fmt,
        datefmt="%Z %Y-%m-%d %H:%M:%S")
    )
    logger.addHandler(logger_handler)

    # return user arguments
    return args

def run_command(cmd):
    # use subprocess.check_output to execute command on shell
    # return None on error
    logger.debug("cmd: \"%s\"" % cmd)
    try:
        out = subprocess.check_output(cmd,shell=True,stderr=subprocess.STDOUT)
        return out
    except subprocess.CalledProcessError as e:
        logger.warn("error executing worker.sh:\n%s" % e)
        logger.warn("stderr:\n%s" % e.output)
        return None

if __name__ == "__main__":
    args = getargs()
    if args.src is None:
        sys.exit("source path or git url is required")
    if args.appId is None:
        sys.exit("appId is required")

    # validate no special characters in appId or vendor
    if not re.search("^[a-zA-Z0-9\.:_]+$", args.vendor):
        sys.exit("invalid vendor name '%s'" % args.vendor)
    if not re.search("^[a-zA-Z0-9\.:_]+$", args.appId):
        sys.exit("invalid appId '%s'" % args.appId)

    logger.info("creating required ACI app store directories")
    # create a clean tmp working directory
    name = "%s_%s" % (args.vendor, args.appId)
    tdir = "/tmp/appbuild/%s" % name
    bdir = "%s/Service/" % tdir
    if os.path.isdir(tdir): 
        logger.debug("remove old directory: %s" % tdir)
        run_command("rm -rfv %s" % tdir) 
    logger.debug("creating new directory: %s" %tdir)
    run_command("mkdir -p %s" % tdir)

    # create required directories
    run_command("mkdir -p %s/UIAssets" % tdir)
    run_command("mkdir -p %s/UIAssets/static" % tdir)
    run_command("mkdir -p %s/Service" % tdir)
    run_command("mkdir -p %s/Image" % tdir)
    run_command("mkdir -p %s/Legal" % tdir)
    run_command("mkdir -p %s/Media" % tdir)

    # pull/copy src code into Service
    if os.path.isdir(args.src):
        logger.debug("copying existing src from: %s" % args.src)
        run_command("cp -rfv %s/* %s" % (args.src, bdir)) 
    else:
        logger.debug("pulling git repository: 'git clone %s %s"%(args.src,tdir))
        run_command("git clone %s %s" % (args.src, bdir))

    # remove git, build, docs, and test files before packaging
    logger.debug("removing .git* files from source directory")
    run_command("rm -rfv %s/Service/.git*" % tdir)
    logger.debug("removing build files from source directory")
    run_command("rm -rfv %s/Service/build*" % tdir)
    logger.debug("removing tests files from source directory")
    run_command("rm -rfv %s/Service/tests*" % tdir)
    logger.debug("removing doc files from source directory")
    run_command("rm -rfv %s/Service/docs*" % tdir)

    # validate app has required directory ./aci_app_store
    app_dir = "%s/Service/aci_app_store" % tdir
    if not os.path.isdir(app_dir):
        logger.error("src code is missing required directory: %s" % app_dir)
        sys.exit(1)
    if not os.path.exists("%s/app.json" % app_dir):
        f = "./aci_app_store/app.json"
        logger.error("src code is missing required file: %s" % f)
        sys.exit(1)

    # move over required and optional files to correct directories
    logger.debug("moving files to prepare for packager")
    run_command("mv %s/app.json %s/app.json" % (app_dir, tdir))
    for d in ["UIAssets", "Service", "Image", "Legal", "Media"]:
        if os.path.exists("%s/%s" % (app_dir, d)):
            run_command("mv %s/%s/* %s/%s/" % (app_dir,d, tdir,d))

    # fixup static/js/common.js and static/css/styles.css files
    logger.debug("using sed to overwrite styles.css and common.js")
    updates = [
        "sed -i 's/var aci_app = false/var aci_app = true/' %s" % (
            "%s/app/static/js/common.js" % bdir),
        "sed -i 's/background: url(\"\/static\/img\/loader.gif\")/%s/' %s" % ( 
            "background: url(\"..\/img\/loader.gif\");",
            "%s/app/static/css/styles.css" % bdir)
    ]
    for c in updates: run_command(c)

    # copy over static files to UIAssets
    if os.path.exists("%s/Service/app/static" % tdir):
        run_command("cp -rfv %s/Service/app/static/* %s/UIAssets/static/" % (
            tdir,tdir))

    # remove aci_app_store directory
    run_command("rm -rfv %s" % app_dir)

    # collect docker image first
    if args.img is None:
        logger.error("Docker image info is required")
        sys.exit(1)
    else:
        dockername = "aci_appcenter_docker_image.tgz"
        if re.search("\.tgz$", args.img):
            if os.path.exists(args.img):
                logger.debug("copying docker image %s to %s/Image/%s" % (
                    args.img, tdir, dockername))
                run_command("cp %s %s/Image/%s" % (args.img, tdir, dockername))
            else:
                m = "Docker image %s not found. " % args.img
                m+= "Try specifying the full path..."
                logger.error(m)
                sys.exit(1)
        else:
            # pull/compress docker image (requires docker to be installed)
            img = args.img.split(":")
            if len(img) == 2: 
                if len(img[0]) == 0 or len(img[1]) == 0:
                    logger.error("invalid image name: %s" % args.img)
                    sys.exit(1)
                cmd = "docker images | egrep \"^%s \" | egrep \"%s\" | wc -l"%(
                    img[0], img[1])
            else:
                cmd = "docker images | egrep \"^%s \" | " % args.img
                cmd+= "egrep \"latest\" | wc -l"

            # notify user that this is slow...
            logger.info("""

    You can drastically speed up build time by pre-downloading and compressing
    your docker image.  For example:
        docker pull %s
        docker save %s | gzip -c > ~/my_docker_image.tgz
        (on future build)
        build_app.sh --img ~/my_docker_image.tgz
            """ % (args.img, args.img))

            ret = run_command(cmd) 
            if ret is None:
                logger.error("failed to execute 'docker images' command")
                sys.exit(1)
            if ret.strip() == "0":
                linfo = "Downloading docker image: %s. " % args.img
                linfo+= "This may take a few minutes..."
                logger.info(linfo)
                ret = run_command("docker pull %s" % args.img)
                if ret is None: 
                    logger.error("Failed to download docker image!")
                    sys.exit(1)
            logger.info("creating compressed docker image from %s" % args.img)
            ret = run_command("docker save %s | gzip -c > %s/Image/%s" % (
                args.img, tdir, dockername))
            if ret is None:
                logger.error("Failed to create compressed docker image")
                sys.exit(1)

    # run packager script
    pkg_args = "python "
    pkg_args+= "./app_package/cisco_aci_app_packager-1.0/"
    pkg_args+= "packager/aci_app_packager.py "
    pkg_args+= "-f %s" % (tdir)    
    if args.key is not None:
        if not os.path.exists(args.key):
            sys.exit("private key %s not accessible" % args.key)
        pkg_args+= " -p %s" % args.key
    logger.info("packaging application")
    output = run_command(pkg_args)
    
    # for convenience, move packaged app into current directory
    successful_build = False
    reg = "App successfully packaged - (?P<path>.+?)\.aci"
    if output is not None:
        r1 = re.search(reg, output)
        if r1 is not None:
            run_command("mv %s.aci ~/" % r1.group("path"))
            s = r1.group("path").split("/")
            logger.info("packaged: ~/%s.aci" % s[-1])
            successful_build = True
    if not successful_build:
        logger.error("Failed to package app:\n%s" % output)
        sys.exit(1) 
    
    
    
   
        
    
    


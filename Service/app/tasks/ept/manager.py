"""
    For direct execution, ensure script is run as a library module:
        python -m app.tasks.manager
    
    @author agossett@cisco.com
"""
from . import utils as ept_utils
from . import node_manager, ep_subscriber
import re, time, traceback, os

# setup logger for this package
import logging
logger = logging.getLogger(__name__)

def manager_job(fabric):
    """ manager_job
        manager is responsible for:
            1) building initial databases
            2) starting and monitoring ep_subscriber (which starts appropriate
                workers processes)
            3) If initial build fails or subscriber exits, manager restarts
    """
    
    # setup logger
    ept_utils.setup_logger(logger, "%s_ep_manager.log" % fabric)
    
    # fresh app since this executed in thread
    app = ept_utils.get_app()

    # manager runs forever
    restart_count = 0
    subscriber = None
    while 1:
        try:
            apic_version = []   # list of controllers and code version
            restart_count+=1
            if restart_count>1:     
                logger.warn("[%s] restarting manager (count:%s)" % (
                    fabric,restart_count))
                time.sleep(5)

            # clear any current fabric_warning
            ept_utils.clear_fabric_warning(fabric)

            # if no username/password has been configured then manually stop
            # manager with appropriate reason
            # add extra check for ACI_APP_CENTER and apic_cert
            config = ept_utils.get_apic_config(fabric)
            apic_cert = False
            if app.config["ACI_APP_MODE"] and "apic_cert" in config \
                and len(config["apic_cert"])>0:
                apic_cert = True
                if not os.path.exists(config["apic_cert"]):
                    ept_utils.add_fabric_event(fabric, "Stopping", 
                        "Certificate file not found", warn=True)
                    return
            if "apic_username" not in config or \
                config["apic_username"] is None:
                logger.warn("username not configured for fabric %s"%fabric)
                ept_utils.add_fabric_event(fabric, "Stopping", 
                    "Credentials not configured", warn=True)
                return
            if not apic_cert and ("apic_password" not in config or \
                config["apic_password"] is None):
                logger.warn("password not configured for fabric %s"%fabric)
                ept_utils.add_fabric_event(fabric, "Stopping", 
                    "Credentials not configured", warn=True)
                return

            ept_utils.add_fabric_event(fabric,"Initializing",
                "Connecting to APIC")
            logger.debug("[%s] connecting to apic" % fabric)
            session = ept_utils.get_apic_session(fabric)
            if not session:
                logger.warn("[%s] failed to create apic session" % fabric)
                ept_utils.add_fabric_event(fabric, "Restarting",
                    "failed to connect to APIC")
                continue

            # get current apic version and add to fabric events for reference
            apic_version = ept_utils.get_controller_version(session)
            if len(apic_version) == 0:
                ept_utils.add_fabric_event(fabric, "Initializing",
                    "failed to determine apic count or apic verson")
            else:
                apic_count = len(apic_version)
                v = None
                v_mismatch = False
                for n in apic_version: 
                    if v is None: v = n["version"]
                    elif v != n["version"]: v_mismatch = True
                if v_mismatch:
                    ept_utils.add_fabric_event(fabric, "Initializing",
                        "version mismatch %s" % ", ".join(
                            ["apic-%s: %s" % (n["node"],n["version"]) \
                                for n in apic_version ])
                    )            
                else:
                    ept_utils.add_fabric_event(fabric, "Initializing",
                        "apic-version: %s, apic-count: %s" % (v, apic_count))

            # determine trust_subscription state 
            trust_subscription = True
            for n in apic_version:
                v = n["version"]
                trust = ep_subscriber.apic_version_trust_subscription(v)
                trust_subscription &= (trust is not None and trust)
            logger.debug("trust subscription autodetect:%r"%trust_subscription)
            if not trust_subscription:
                msg = "APIC versions < 2.2.1n. Websocket subscriptions to EPM "
                msg+= "concrete objects are unreliable which require an API "
                msg+= "query to each leaf on each endpoint event. If there "
                msg+= "are a high number of endpoint events, you may see high "
                msg+= "cpu on nginx process on all leaves. "
                msg+= "It is highly recommended to upgrade all APICs and "
                msg+= "leaves >= 2.2.1n before monitoring with this application"
                ept_utils.add_fabric_event(fabric,"Initializing",msg,warn=True)
            
            if config["trust_subscription"] == "auto": pass
            elif config["trust_subscription"] == "no":trust_subscription = False
            else: trust_subscription = True
            logger.debug("final trust subscription: %r"%trust_subscription)


            # get overlay-1 vnid for fabric
            logger.debug("[%s] getting overlay-1 vnid" % fabric)
            overlay_vnid = ept_utils.get_overlay_vnid(session)
            if overlay_vnid is None:
                logger.warn("[%s] failed to get overlay-1 vnid" % fabric)
                ept_utils.add_fabric_event(fabric, "Restarting",
                    "failed to initialize overlay VNID")
                continue

            # build inital node db
            ept_utils.add_fabric_event(fabric, "Initializing",
                "Building node database")
            logger.debug("[%s] building initial node db" % fabric)
            if not node_manager.build_initial_node_db(fabric, session, app):
                logger.error("[%s] failed to build initial node db" % fabric)
                ept_utils.add_fabric_event(fabric, "Restarting",
                    "failed to initialize node database")
                continue

            # build vpc node db (best effort, no restart on failure)
            ept_utils.add_fabric_event(fabric, "Initializing",
                "Building vpc database")
            logger.debug("[%s] building vpc node db" % fabric)
            node_manager.build_vpc_node_db(fabric, session, app)
            # build port-channel to vpc mapping
            logger.debug("[%s] building port-channel to vpc mapping" % fabric)
            if not node_manager.build_vpc_config_db(fabric, session, app):
                logger.error("[%s] failed to build pc to vpc mapping" % fabric)
                ept_utils.add_fabric_event(fabric, "Restarting",
                    "failed to initialize vpc database")
                continue

            # build initial tunnel db
            ept_utils.add_fabric_event(fabric, "Initializing",
                "Building tunnel database")
            logger.debug("[%s] building initial tunnel db" % fabric)
            if not node_manager.build_initial_tunnel_db(fabric, session, app):
                logger.error("[%s] failed to build tunnel db" % fabric)
                ept_utils.add_fabric_event(fabric, "Restarting",
                    "failed to initialize tunnel database")
                continue

            # build initial name db (and epgs_to_bd_vnid)
            ept_utils.add_fabric_event(fabric, "Initializing",
                "Building name database")
            logger.debug("[%s] building initial ep_vnids/ep_epgs db" % fabric)
            if not node_manager.build_initial_name_db(fabric, session, app):
                logger.error("[%s] failed to build name db" % fabric)
                ept_utils.add_fabric_event(fabric, "Restarting",
                    "failed to initialize name database")
                continue
            if not node_manager.build_initial_epg_to_bd_vnid_db(fabric, 
                session, app):
                logger.error("[%s] failed to build epg_to_bd_vnid_db" % fabric)
                ept_utils.add_fabric_event(fabric, "Restarting",
                    "failed to initialize name database")
                continue

            # build initial subnet db
            ept_utils.add_fabric_event(fabric, "Initializing",
                "Building subnets database")
            logger.debug("[%s] building initial subnets db" % fabric)
            if not node_manager.build_initial_subnets_db(fabric, session, app):
                logger.error("[%s] failed to build subnet db" % fabric)
                ept_utils.add_fabric_event(fabric, "Restarting",
                    "failed to initialize subnets database")
                continue

            # build initial ep_history db
            ept_utils.add_fabric_event(fabric, "Initializing",
                "Building endpoint database")
            logger.debug("[%s] building initial ep_history db" % fabric)
            rebuild_jobs = ep_subscriber.stage_ep_history_db(fabric, 
                session, app, overlay_vnid)
            if rebuild_jobs is None:
                logger.error("[%s] failed to build ep_history db" % fabric)
                ept_utils.add_fabric_event(fabric, "Restarting",
                    "failed to initialize endpoint database")
                continue 
 
            # start subscriber - it sets fabric state to running on success
            subscriber = ep_subscriber.EPSubscriber(fabric, overlay_vnid)
            subscriber.trust_subscription = trust_subscription
            subscriber.rebuild_jobs = rebuild_jobs
            subscriber.subscribe_to_objects()
            ept_utils.add_fabric_event(fabric, "Restarting", 
                "APIC subscription closed") 
    
        except Exception as e:
            logger.error("[%s] Exception: %s"%(fabric, traceback.format_exc()))
            ept_utils.add_fabric_event(fabric, "Restarting",
                "An exception occurred (%s)" % e)
            
        finally:
            # best effort stop child processes if running
            if subscriber is not None:
                try: subscriber.stop_workers()
                except Exception as e: pass

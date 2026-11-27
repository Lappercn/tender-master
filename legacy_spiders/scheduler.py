#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
爬虫定时调度器
每天下午3:50开始，每隔3分钟依次启动一个爬虫脚本
启动顺序：cfcpn_spider.py -> login_spider.py -> cebpub.py -> tobacco_spider.py
"""

import schedule
import subprocess
import logging
import time
import os
import sys
from datetime import datetime, timedelta
import threading
import signal
import argparse
import locale

# 日志配置
def setup_logging():
    """配置日志系统"""
    # 确保logs目录存在
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # 配置日志格式
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(log_dir, "scheduler.log"), mode='a', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger(__name__)

# 全局变量
logger = setup_logging()
scheduler_instance = None  # 全局调度器实例
stop_scheduler = False  # 停止调度器的标志

class CrawlerScheduler:
    def __init__(self):
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.scripts = [
            "cfcpn_spider.py",
            "login_spider.py", 
            "cebpubservice_spider.py",
            "tobacco_spider.py",
            "guotie_spider.py",
            "plap_spider.py"
        ]
        self.current_script_index = 0
        self.daily_start_time = "15:40"  # 下午3:40
        self.interval_minutes = 5  # 每隔5分钟
        self.max_runtime_hours = 2  # 最大运行时间2小时
        self.failed_scripts = []  # 本轮失败列表
        self.retried_scripts = set()  # 已重试过的脚本
        
        # 将全局状态移入实例
        self.running_processes = {}
        self.log_file_handles = {}

    def cleanup_old_logs(self, days=7):
        """清理旧日志文件"""
        try:
            log_dir = "logs"
            if not os.path.exists(log_dir):
                return
            
            cutoff_time = datetime.now() - timedelta(days=days)
            count = 0
            
            for filename in os.listdir(log_dir):
                file_path = os.path.join(log_dir, filename)
                if not os.path.isfile(file_path):
                    continue
                    
                # 检查文件修改时间
                file_mtime = datetime.fromtimestamp(os.path.getmtime(file_path))
                if file_mtime < cutoff_time:
                    try:
                        os.remove(file_path)
                        count += 1
                    except Exception as e:
                        logger.warning(f"删除过期日志 {filename} 失败: {e}")
            
            if count > 0:
                logger.info(f"🧹 已清理 {count} 个过期日志文件（{days}天前）")
        except Exception as e:
            logger.error(f"❌ 清理日志文件时出错: {e}")

    def check_script_exists(self, script_name):
        """检查脚本文件是否存在"""
        script_path = os.path.join(self.script_dir, script_name)
        return os.path.exists(script_path)
    
    def start_script(self, script_name):
        """启动单个爬虫脚本"""
        try:
            script_path = os.path.join(self.script_dir, script_name)
            
            # 检查脚本是否存在
            if not self.check_script_exists(script_name):
                logger.error(f"脚本文件不存在: {script_path}")
                return False
            
            # 检查是否已有同名进程在运行
            if script_name in self.running_processes:
                old_process = self.running_processes[script_name]
                if old_process.poll() is None:  # 进程仍在运行
                    logger.warning(f"脚本 {script_name} 仍在运行中，跳过本次启动")
                    return False
                else:
                    # 清理已结束的进程
                    del self.running_processes[script_name]
            
            # 准备日志文件，避免PIPE阻塞导致子进程挂起
            timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
            per_script_log = os.path.join("logs", f"{os.path.splitext(script_name)[0]}_{timestamp_str}.log")
            # 以文本方式追加写入，使用行缓冲
            log_fh = open(per_script_log, mode='a', encoding='utf-8', buffering=1)

            # 启动新进程
            logger.info(f"🚀 开始启动脚本: {script_name}")
            
            # 根据脚本类型选择不同的启动参数
            if script_name == "cfcpn_spider.py":
                cmd = [sys.executable, script_path]  # 默认已无头
            elif script_name == "login_spider.py":
                cmd = [sys.executable, script_path, "test"]
            elif script_name == "cebpubservice_spider.py":
                cmd = [sys.executable, script_path, "--now"]
            elif script_name == "tobacco_spider.py":
                cmd = [sys.executable, script_path]  # 默认已无头
            elif script_name == "guotie_spider.py":
                cmd = [sys.executable, script_path]  # 默认无头模式
            elif script_name == "plap_spider.py":
                cmd = [sys.executable, script_path]  # 默认无头模式
            else:
                cmd = [sys.executable, script_path]
            
            # 启动进程
            creationflags = 0
            start_new_session = False
            if os.name == 'nt':
                # 在Windows上创建新的进程组，便于整树终止（包含Chrome）
                creationflags = getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0)
            else:
                # 在POSIX上以新会话启动，便于killpg
                start_new_session = True

            process = subprocess.Popen(
                cmd,
                cwd=self.script_dir,
                stdout=log_fh,
                stderr=log_fh,
                text=True,
                encoding=locale.getpreferredencoding(False),
                errors='replace',
                creationflags=creationflags,
                start_new_session=start_new_session
            )
            
            self.running_processes[script_name] = process
            self.log_file_handles[script_name] = log_fh
            logger.info(f"✅ 脚本 {script_name} 启动成功，PID: {process.pid}")
            
            # 启动监控线程
            monitor_thread = threading.Thread(
                target=self.monitor_process,
                args=(script_name, process),
                daemon=True
            )
            monitor_thread.start()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ 启动脚本 {script_name} 失败: {e}")
            # 失败时关闭已打开的日志文件句柄
            try:
                if 'log_fh' in locals() and not log_fh.closed:
                    log_fh.close()
            except Exception:
                pass
            return False
    
    def monitor_process(self, script_name, process):
        """监控进程运行状态"""
        try:
            start_time = datetime.now()
            max_runtime = timedelta(hours=self.max_runtime_hours)
            
            while True:
                # 检查进程是否结束
                if process.poll() is not None:
                    # 进程已结束
                    try:
                        process.wait(timeout=1)
                    except Exception:
                        pass
                    end_time = datetime.now()
                    runtime = end_time - start_time
                    
                    if process.returncode == 0:
                        logger.info(f"✅ 脚本 {script_name} 正常结束，运行时间: {runtime}")
                    else:
                        logger.error(f"❌ 脚本 {script_name} 异常结束，返回码: {process.returncode}，运行时间: {runtime}")
                        # 记录失败用于后续重试（仅在未重试过时加入）
                        if script_name not in self.retried_scripts:
                            if script_name not in self.failed_scripts:
                                self.failed_scripts.append(script_name)
                    
                    # 清理进程记录
                    if script_name in self.running_processes:
                        del self.running_processes[script_name]
                    # 关闭日志文件
                    try:
                        fh = self.log_file_handles.pop(script_name, None)
                        if fh and not fh.closed:
                            fh.flush()
                            fh.close()
                    except Exception:
                        pass
                    break
                
                # 检查是否超时
                current_time = datetime.now()
                if current_time - start_time > max_runtime:
                    logger.warning(f"⏰ 脚本 {script_name} 运行超时({self.max_runtime_hours}小时)，强制终止")
                    self._terminate_process_tree(process)
                    # 记录超时失败（仅在未重试过时加入）
                    if script_name not in self.retried_scripts:
                        if script_name not in self.failed_scripts:
                            self.failed_scripts.append(script_name)
                    
                    # 清理进程记录
                    if script_name in self.running_processes:
                        del self.running_processes[script_name]
                    # 关闭日志文件
                    try:
                        fh = self.log_file_handles.pop(script_name, None)
                        if fh and not fh.closed:
                            fh.flush()
                            fh.close()
                    except Exception:
                        pass
                    break
                
                # 等待10秒后再次检查
                time.sleep(10)
                
        except Exception as e:
            logger.error(f"❌ 监控进程 {script_name} 时出错: {e}")
    
    def start_next_script(self):
        """启动下一个脚本"""
        if self.current_script_index >= len(self.scripts):
            logger.info(f"🎉 所有脚本已启动完成 (共{len(self.scripts)}个脚本)")
            logger.info(f"📈 当前运行中进程数: {len(self.running_processes)}")
            if self.running_processes:
                logger.info(f"🔄 运行中的脚本: {list(self.running_processes.keys())}")
            return
        
        script_name = self.scripts[self.current_script_index]
        logger.info(f"📋 准备启动第 {self.current_script_index + 1} 个脚本: {script_name}")
        
        if self.start_script(script_name):
            self.current_script_index += 1
            
            # 如果还有脚本需要启动，安排下一次启动
            if self.current_script_index < len(self.scripts):
                next_script = self.scripts[self.current_script_index]
                logger.info(f"⏰ {self.interval_minutes}分钟后将启动: {next_script}")
        else:
            logger.error(f"❌ 脚本 {script_name} 启动失败，跳过")
            self.current_script_index += 1
    
    def daily_job(self):
        """每日定时任务"""
        logger.info("="*60)
        logger.info(f"🌅 开始执行每日爬虫任务 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info("="*60)

        # 1. 清理旧日志
        self.cleanup_old_logs()
        
        # 清理之前的一次性任务，避免重复执行
        # 清理脚本启动任务
        for i in range(1, len(self.scripts)):
            schedule.clear(f'script_launch_{i}')
        # 清理重试任务
        schedule.clear('retry_once_tag')
        # 清理所有可能的重试任务tag（最多支持10个重试脚本）
        for i in range(1, 11):
            schedule.clear(f'retry_scripts_{i}')
        
        # 重置脚本索引
        self.current_script_index = 0
        # 重置失败与重试状态
        self.failed_scripts = []
        self.retried_scripts = set()
        
        # 检查所有脚本文件
        missing_scripts = []
        for script in self.scripts:
            if not self.check_script_exists(script):
                missing_scripts.append(script)
        
        if missing_scripts:
            logger.error(f"❌ 以下脚本文件不存在: {missing_scripts}")
            logger.error("请检查脚本文件是否存在于当前目录")
            return
        
        # 启动第一个脚本
        self.start_next_script()
        
        # 安排后续脚本的启动（按顺序，每个间隔interval_minutes分钟）
        for i in range(1, len(self.scripts)):
            delay_minutes = i * self.interval_minutes
            # 为每个脚本启动任务添加唯一的tag
            script_tag = f'script_launch_{i}'
            self._schedule_once_after_minutes(delay_minutes, self._schedule_next_script, script_tag)

        # 在一轮结束后安排重试（一次性）：总时长 + 缓冲1分钟
        total_delay = len(self.scripts) * self.interval_minutes + 1
        def schedule_retry_once():
            try:
                self.retry_failed_scripts_once()
            finally:
                # 重试完成后清理该一次性任务
                schedule.clear('retry_once_tag')
        self._schedule_once_after_minutes(total_delay, schedule_retry_once, 'retry_once_tag')
    
    def _schedule_once_after_minutes(self, delay_minutes, job_func=None, tag=None):
        """在指定分钟后只执行一次任务"""
        if job_func is None:
            job_func = self._schedule_next_script
            
        # 使用schedule的seconds.after方法来安排延迟执行的任务
        def once_job():
            try:
                job_func()
            finally:
                # 执行后立即移除当前任务，避免重复执行
                if tag:
                    schedule.clear(tag)
                else:
                    # 如果没有tag，需要手动移除这个job
                    schedule.cancel_job(job)
        
        # 安排任务在指定秒数后执行
        job = schedule.every(delay_minutes * 60).seconds.do(once_job)
        if tag:
            job.tag(tag)
        return job
    
    def _schedule_next_script(self):
        """安排下一个脚本的启动"""
        # 直接调用start_next_script，让它自己处理索引递增
        self.start_next_script()

    def stop_and_cleanup_process(self, script_name):
        """结束并清理指定脚本的进程（如果还在运行）"""
        try:
            proc = self.running_processes.get(script_name)
            if proc and proc.poll() is None:
                logger.info(f"🛑 终止重试前仍在运行的进程: {script_name} (PID: {proc.pid})")
                self._terminate_process_tree(proc)
            if script_name in self.running_processes:
                del self.running_processes[script_name]
            # 关闭日志文件
            try:
                fh = self.log_file_handles.pop(script_name, None)
                if fh and not fh.closed:
                    fh.flush()
                    fh.close()
            except Exception:
                pass
        except Exception as e:
            logger.warning(f"终止进程 {script_name} 时出错: {e}")

    def _terminate_process_tree(self, process_obj):
        """终止整个子进程树（包含浏览器等子进程）"""
        try:
            pid = process_obj.pid
            if os.name == 'nt':
                # Windows: 使用taskkill 杀死整个进程树
                subprocess.run([
                    'taskkill', '/PID', str(pid), '/T', '/F'
                ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                # POSIX: 杀死进程组
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                    # 等待片刻再强杀
                    time.sleep(3)
                    os.killpg(os.getpgid(pid), signal.SIGKILL)
                except Exception:
                    # 如果失败，回退到直接kill
                    try:
                        process_obj.terminate()
                        process_obj.wait(timeout=5)
                    except Exception:
                        try:
                            process_obj.kill()
                        except Exception:
                            pass
        except Exception as _e:
            logger.warning(f"结束进程树时发生异常: {_e}")

    def retry_failed_scripts_once(self):
        """对本轮失败的脚本重试一次（顺序执行，间隔同样的间隔时间）"""
        if not self.failed_scripts:
            logger.info("✅ 本轮没有失败脚本需要重试")
            return

        retry_list = list(self.failed_scripts)
        logger.info(f"🔁 开始重试失败脚本（最多一次）：{retry_list}")

        # 清空失败列表，避免重复加入；通过 retried_scripts 标记已重试
        self.failed_scripts = []

        # 顺序重试：先立即重试第一个，后续按间隔安排
        def _retry_one(script_name):
            # 标记已重试
            self.retried_scripts.add(script_name)
            # 确保不存在旧进程
            self.stop_and_cleanup_process(script_name)
            # 启动
            started = self.start_script(script_name)
            if started:
                logger.info(f"🔁 已重试启动: {script_name}")
            else:
                logger.error(f"❌ 重试启动失败: {script_name}")

        # 立即重试第一个
        _retry_one(retry_list[0])

        # 其余的按间隔分钟加入计划（使用一次性任务）
        for i in range(1, len(retry_list)):
            name = retry_list[i]
            delay_minutes = i * self.interval_minutes
            def _make_job(nm):
                return lambda: _retry_one(nm)
            retry_tag = f'retry_scripts_{i}'
            self._schedule_once_after_minutes(delay_minutes, _make_job(name), retry_tag)
    
    def get_status(self):
        """获取当前状态"""
        status_info = {
            'current_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'running_processes': len(self.running_processes),
            'next_daily_run': None,
            'process_details': []
        }
        
        # 获取下次运行时间
        jobs = schedule.get_jobs('daily')
        if jobs:
            next_run = min(job.next_run for job in jobs)
            status_info['next_daily_run'] = next_run.strftime('%Y-%m-%d %H:%M:%S')
        
        # 获取进程详情
        for script_name, process in self.running_processes.items():
            status_info['process_details'].append({
                'script': script_name,
                'pid': process.pid,
                'status': 'running' if process.poll() is None else 'finished'
            })
        
        return status_info
    
    def stop_all_processes(self):
        """停止所有正在运行的进程"""
        logger.info("🛑 开始停止所有正在运行的爬虫进程...")
        
        for script_name, process in list(self.running_processes.items()):
            try:
                if process.poll() is None:  # 进程仍在运行
                    logger.info(f"停止进程(含子进程树): {script_name} (PID: {process.pid})")
                    self._terminate_process_tree(process)
                
                del self.running_processes[script_name]
                # 关闭日志文件
                try:
                    fh = self.log_file_handles.pop(script_name, None)
                    if fh and not fh.closed:
                        fh.flush()
                        fh.close()
                except Exception:
                    pass
                
            except Exception as e:
                logger.error(f"❌ 停止进程 {script_name} 时出错: {e}")
        
        logger.info("✅ 所有进程已停止")

def signal_handler(signum, frame):
    """信号处理器"""
    global stop_scheduler
    logger.info(f"\n🛑 接收到信号 {signum}，准备停止调度器...")
    stop_scheduler = True
    
    # 停止所有进程
    if scheduler_instance:
        scheduler_instance.stop_all_processes()
    
    # 清理定时任务
    schedule.clear()
    
    logger.info("👋 调度器已停止")
    sys.exit(0)

def main():
    """主函数"""
    global stop_scheduler, scheduler_instance
    
    # 命令行参数
    parser = argparse.ArgumentParser(description="爬虫定时调度器")
    parser.add_argument("--now", action="store_true", help="立即执行一次定时任务，然后继续常规调度")
    parser.add_argument("--once", action="store_true", help="仅执行一次定时任务，等待所有子进程结束后退出")
    args = parser.parse_args()

    # 注册信号处理器
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # 终止信号
    
    logger.info("🚀 爬虫定时调度器启动")
    
    # 创建全局调度器实例
    scheduler_instance = CrawlerScheduler()
    
    logger.info(f"📁 工作目录: {os.getcwd()}")
    logger.info(f"⏰ 每日启动时间: {scheduler_instance.daily_start_time}")
    logger.info(f"⏱️ 脚本间隔: {scheduler_instance.interval_minutes}分钟")
    
    # 安排每日任务
    schedule.every().day.at(scheduler_instance.daily_start_time).do(scheduler_instance.daily_job).tag('daily')
    
    logger.info(f"📅 已安排每日任务，下次运行时间: {schedule.get_jobs('daily')[0].next_run}")

    # 立即执行一次（并继续调度）
    if args.now:
        logger.info("⚡ 收到 --now 参数，立即执行一次定时任务")
        scheduler_instance.daily_job()

    # 仅执行一次并退出
    if args.once:
        logger.info("⚡ 收到 --once 参数，立即执行一次定时任务并在完成后退出")
        scheduler_instance.daily_job()
        # 运行主循环直到所有任务完成
        try:
            while not stop_scheduler:
                schedule.run_pending()
                # 如果所有脚本都已启动并且没有运行中的进程，则退出
                if (scheduler_instance.current_script_index >= len(scheduler_instance.scripts) and 
                    not scheduler_instance.running_processes):
                    break
                time.sleep(30)  # 每30秒检查一次
        except KeyboardInterrupt:
            logger.info("\n🛑 接收到键盘中断信号")
        except Exception as e:
            logger.error(f"❌ 调度器运行出错: {e}")
        finally:
            if scheduler_instance:
                scheduler_instance.stop_all_processes()
            schedule.clear()
        logger.info("👋 单次任务已完成，调度器退出")
        return
    
    # 主循环
    try:
        last_status_log = datetime.now()
        while not stop_scheduler:
            schedule.run_pending()
            
            # 每10分钟输出一次状态信息
            current_time = datetime.now()
            if current_time - last_status_log >= timedelta(minutes=10):
                pending_jobs = len(schedule.get_jobs())
                daily_jobs = len(schedule.get_jobs('daily'))
                logger.info(f"📊 调度器状态 - 待执行任务: {pending_jobs}, 每日任务: {daily_jobs}, 运行中进程: {len(scheduler_instance.running_processes)}")
                if schedule.get_jobs('daily'):
                    next_daily = min(job.next_run for job in schedule.get_jobs('daily'))
                    logger.info(f"⏰ 下次每日任务时间: {next_daily.strftime('%Y-%m-%d %H:%M:%S')}")
                last_status_log = current_time
            
            time.sleep(30)  # 每30秒检查一次
            
    except KeyboardInterrupt:
        logger.info("\n🛑 接收到键盘中断信号")
    except Exception as e:
        logger.error(f"❌ 调度器运行出错: {e}")
    finally:
        # 清理工作
        if scheduler_instance:
            scheduler_instance.stop_all_processes()
        schedule.clear()
        logger.info("👋 调度器已退出")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3

# import libraries
import os
import re
import sys
import math
import argparse
import subprocess


"""
Initial sanity checks
"""
# Directory check
if not re.match('/nas/content/(live|staging)/\w+', os.getcwd()):
    sys.exit("This command needs to be run within an install's directory.")

# Root avoidance
if os.environ.get('USERNAME') == 'root':
    sys.exit('dbsummary works without running as root!',
             'Please try as your regular user.')


"""
Initial variable definition functions
"""


class Colors():

    # Color effects
    reset = '\033[0m'

    class fg:
        # Foreground colors:
        red = '\033[91m'
        green = '\033[92m'
        yellow = '\033[93m'
        blue = '\033[94m'
        cyan = '\033[96m'


def get_site_name():
    # Get site name from current working directory
    return os.getcwd().split('/')[4]


def get_environment():
    # Get site environment from current working directory
    return os.getcwd().split('/')[3]


def get_table_prefix(env, site):
    # Get table_prefix from wp-config.php file
    try:
        with open("/nas/content/{}/{}/wp-config.php".format(env, site), "r") as conf:
            for line in conf.readlines():
                # this is fragile.
                if 'table_prefix' in line:
                    return line.split("'")[1]
    except FileNotFoundError:
        print("wp-config.php file not found in {}{} {}{}{} root directory".format(
              Colors.fg.red, Colors.fg.yellow, site, env, Colors.reset))
        sys.exit()


def get_dbname():
    # build database name from environment variables
    if env == 'staging':
        db_prefix = "snapshot_"
    else:
        db_prefix = "wp_"
    return db_prefix + site


def fix_format(size_bytes):
    # human readable format converter
    if size_bytes <= 0:
        return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return '{} {}'.format(s, size_name[i])


def run_query(query, data_only=True):
    """Run db query using wp-cli
    :param query: query to run
    :param data_only: bool, exclude column names
    :return: string of query results
    """
    cmd = ['wp', 'db', 'query', '--skip-plugins', '--skip-themes', query]
    if data_only:
        cmd.append('--skip-column-names')
    return subprocess.check_output(cmd).decode('utf-8').strip()


def check_config(site, option):
    cmd = ['php', '/nas/wp/www/tools/wpe.php', 'option-get', site, option]
    return subprocess.check_output(cmd).decode('utf-8').strip()


def get_subsite_count():
    # get a count of subsites for multisite
    return run_query(
        "SELECT COUNT(*) FROM {}blogs WHERE blog_id > 1;".format(table_prefix), data_only=True)


def get_core_version():
    # get WP core version
    core_cmd = ['wp', 'core', 'version']
    return subprocess.check_output(core_cmd).decode('utf-8').strip()


def get_dbsize():
    # calculate total database size
    db_size = run_query("SELECT SUM(data_length + index_length)\
                        FROM information_schema.TABLES\
                        WHERE table_schema = '{}'\
                          and TABLE_TYPE='BASE TABLE';".format(db_name), data_only=True)
    return fix_format(int(db_size))


def print_header():
    # printer header output
    print("{}Install: {}{:<19}".format(Colors.fg.blue, Colors.fg.cyan, site),
          "{}Database: {}{:<19}".format(Colors.fg.blue, Colors.fg.cyan, db_name),
          "{}Size: {}{}".format(Colors.fg.blue, Colors.fg.cyan, db_size))
    multisite = check_config(site, "mu")
    if not multisite:
        print("{}WP Core: {}{}\n".format(Colors.fg.blue, Colors.fg.cyan, core_version))
    else:
        subsites = get_subsite_count()
        multisite = "Yes"
        print("{}WP Core: {}{:<19}".format(Colors.fg.blue, Colors.fg.cyan, core_version),
              "{}Multisite: {}{:<18}".format(Colors.fg.blue, Colors.fg.cyan, multisite),
              "{}Subsite Count: {}{}\n".format(Colors.fg.blue, Colors.fg.cyan, subsites))


def build_count_dictionary():
    # build and store dictionary of counts for optimization variables
    opt_dictionary = {
        "rows": run_query("SELECT SUM(table_rows)\
                          FROM information_schema.TABLES\
                          WHERE table_schema = '{}'\
                            and TABLE_TYPE='BASE TABLE';".format(db_name), data_only=True),
        "tables": run_query("SELECT COUNT(TABLE_NAME)\
                            FROM information_schema.TABLES\
                            WHERE table_schema = '{}'\
                              and TABLE_TYPE='BASE TABLE';".format(db_name), data_only=True),
        "myisam": run_query("SELECT COUNT(Engine)\
                            FROM information_schema.TABLES\
                            WHERE table_schema = '{}'\
                              and TABLE_TYPE='BASE TABLE'\
                              and Engine='MyISAM';".format(db_name), data_only=True),
        "innodb": run_query("SELECT COUNT(Engine)\
                            FROM information_schema.TABLES\
                            WHERE table_schema = '{}'\
                              and TABLE_TYPE='BASE TABLE'\
                              and Engine='InnoDB';".format(db_name), data_only=True),
        "myrows": run_query("SELECT SUM(table_rows)\
                            FROM information_schema.TABLES\
                            WHERE table_schema = '{}'\
                              and TABLE_TYPE='BASE TABLE'\
                              and Engine='MyISAM';".format(db_name), data_only=True),
        "inrows": run_query("SELECT SUM(table_rows)\
                            FROM information_schema.TABLES\
                            WHERE table_schema = '{}'\
                              and TABLE_TYPE='BASE TABLE'\
                              and Engine='InnoDB';".format(db_name), data_only=True),
        "autoloads": run_query("SELECT SUM(LENGTH(option_value))\
                               FROM {}options\
                               WHERE autoload='yes';".format(table_prefix), data_only=True),
        "revisions": run_query("SELECT COUNT(*)\
                               FROM {}posts\
                               WHERE post_type='revision';".format(table_prefix), data_only=True),
        "trash_posts": run_query("SELECT COUNT(*)\
                                 FROM {}posts\
                                 WHERE post_type='trash';".format(table_prefix), data_only=True),
        "spam_comments": run_query("SELECT COUNT(*)\
                                   FROM {}comments\
                                   WHERE comment_approved='spam';".format(table_prefix), data_only=True),
        "trash_comments": run_query("SELECT COUNT(*)\
                                    FROM {}comments\
                                    WHERE comment_approved='trash';".format(table_prefix), data_only=True),
        "orphaned_postmeta": run_query("SELECT COUNT(pm.meta_id)\
                                       FROM {}postmeta pm\
                                       LEFT JOIN {}posts wp\
                                            ON wp.ID = pm.post_id\
                                       WHERE wp.ID IS NULL;".format(table_prefix, table_prefix), data_only=True),
        "orphaned_commentmeta": run_query("SELECT COUNT(*)\
                                          FROM {}commentmeta\
                                          WHERE comment_id\
                                          NOT IN(SELECT comment_id\
                                                 FROM {}comments);".format(table_prefix, table_prefix), data_only=True),
        "transients": run_query("SELECT COUNT(*)\
                                FROM {}options\
                                WHERE option_name\
                                LIKE ('%_transient_%');".format(table_prefix), data_only=True),
    }
    return opt_dictionary


def print_optimization_variables(counts):
    # print out table and row counts by storage engine
    print("{}Tables and Rows counts:".format(Colors.fg.red))
    print("{}MyISAM tables: {}{:<13}".format(Colors.fg.blue, Colors.fg.cyan, counts['myisam']),
          "{}InnoDB tables: {}{:<14}".format(Colors.fg.blue, Colors.fg.cyan, counts['innodb']),
          "{}Total tables: {}{}".format(Colors.fg.blue, Colors.fg.cyan, counts['tables']))
    print("{}MyISAM rows: {}{:<15}".format(Colors.fg.blue, Colors.fg.cyan, counts['myrows']),
          "{}InnoDB rows: {}{:<16}".format(Colors.fg.blue, Colors.fg.cyan, counts['inrows']),
          "{}Total rows: {}{}\n".format(Colors.fg.blue, Colors.fg.cyan, counts['rows']))
    if int(counts['myisam']) > 0:  # If any MyISAM tables, recommend conversion to InnoDB
        print("{}Recommendation: {}Convert MyISAM tables to InnoDB.\n".format(Colors.fg.red, Colors.fg.cyan))
    else:
        pass
    # print out key optimization variables
    print("{}Key Optimization Variables:".format(Colors.fg.red))
    print("{}Revisions: {}{:<17}".format(Colors.fg.blue, Colors.fg.cyan, counts['revisions']),
          "{}Trashed Posts: {}{:<14}".format(
              Colors.fg.blue, Colors.fg.cyan, counts['trash_posts']),
          "{}Orphaned Postmeta: {}{}".format(Colors.fg.blue, Colors.fg.cyan, counts['orphaned_postmeta']))
    print("{}Spam Comments: {}{:<13}".format(Colors.fg.blue, Colors.fg.cyan, counts['spam_comments']),
          "{}Trash Comments: {}{:<13}".format(
              Colors.fg.blue, Colors.fg.cyan, counts['trash_comments']),
          "{}Orphaned Commentmeta: {}{}\n".format(Colors.fg.blue, Colors.fg.cyan, counts['orphaned_commentmeta']))
    if (int(counts['revisions']) + int(counts['trash_posts']) + int(counts['orphaned_postmeta']) +
       int(counts['spam_comments']) + int(counts['trash_comments']) + int(counts['orphaned_commentmeta'])) > 0:
        print("{}Recommendation: {}Review options for cleanup in Overdrive > Queries.\n".format(
              Colors.fg.red, Colors.fg.cyan))
    else:
        pass
    # if autoloads are over 800KB, get a listing of top 5 autoloads by size
    if int(counts['autoloads']) >= 800000:
        print("{}Autoload Data: {}{}".format(
            Colors.fg.red, Colors.fg.cyan, fix_format(int(counts['autoloads']))))
        print("{}Top 5 autoload items by size:{}\n".format(Colors.fg.blue, Colors.fg.cyan))
        print(run_query("SELECT LENGTH(option_value), option_name\
                  FROM {}options\
                  WHERE autoload='yes'\
                  ORDER BY length(option_value)\
                  DESC LIMIT 5;".format(table_prefix)), "\n")
        print("{}Recommendation: {}Execute {}dbautoload{} command for full autoload report.".format(
              Colors.fg.red, Colors.fg.cyan, Colors.fg.yellow, Colors.fg.cyan))
        obj_cache = check_config(site, "use_object_cache")  # Check if object_cache is enabled
        if obj_cache:
            print("{}Recommendation: {}Object cache{} is {}enabled{}.  Recommend disable.".format(
                   Colors.fg.red, Colors.fg.yellow, Colors.fg.cyan, Colors.fg.red, Colors.fg.cyan))
        else:
            print("{}Object cache{} is {}disabled{}.".format(
                   Colors.fg.yellow, Colors.fg.cyan, Colors.fg.green, Colors.fg.cyan))
    else:
        print("{}Autoload Data: {}{}".format(
            Colors.fg.red, Colors.fg.green, fix_format(int(counts['autoloads']))))


def print_tables(engine, sortby, tblnum):
    # print out table by storage engine and sorted by provided parsed argument
    # Sorts by row by default, but use --size or -s to sort by total size
    print()
    # Sanity check for customizable table counter selection
    if (engine == "MyISAM") and (int(counts['myisam']) < tblnum):
        rowcount = int(counts['myisam']) + 1
    elif (engine == "InnoDB") and (int(counts['innodb']) < tblnum):
        rowcount = int(counts['innodb']) + 1
    else:
        rowcount = tblnum + 1
    # Begin table construction
    print("{}Top 10 {}{}{} Tables sorted by rows: {}{}\n".format(
          Colors.fg.blue, Colors.fg.yellow, engine, Colors.fg.blue, Colors.fg.yellow, db_name))
    innodb_tables = run_query("SELECT TABLE_NAME as 'Table',\
                                      Engine,\
                                      table_rows as 'Rows',\
                                      round(((data_length) / 1024 / 1024), 2) as 'Data_in_MB',\
                                      round(((index_length) / 1024 / 1024), 2) as 'Index_in_MB',\
                                      round(((data_length + index_length) / 1024 / 1024), 2) as 'Total_size_MB'\
                              FROM information_schema.TABLES\
                              WHERE table_schema = '{}'\
                                and TABLE_TYPE = 'BASE TABLE'\
                                and Engine = '{}'\
                              ORDER BY {}\
                              DESC LIMIT {};".format(db_name, engine, sortby, rowcount), data_only=True)
    table_lines = []
    for line in innodb_tables.splitlines():
        table_lines.append(line.split())
    header = "{}{:<50}{:<8}{:>9}{:>16}{:>13}{:>16}"
    headerline = "{:<50}{:<10}{:<13}{:>10}{:>13}{:>16}"
    body = "{:<50}{:<10}{:<13}{:>10}{:>13}{:>16}"
    print(header.format(Colors.fg.green, table_lines[0][0], table_lines[0][1], table_lines[0][2],
                        table_lines[0][3], table_lines[0][4], table_lines[0][5]))
    print(headerline.format(
        '----------------', '------', '----------', '----------', '-----------', '-------------'), Colors.fg.cyan)
    for row in range(1, (rowcount)):
        print(body.format(table_lines[row][0], table_lines[row][1], table_lines[row][2],
                          table_lines[row][3], table_lines[row][4], table_lines[row][5]))


if __name__ == '__main__':
    # Parse arguments - if no argument provided, sort table listing by row in descending order
    parser = argparse.ArgumentParser(description='Database summary for current install.')
    parser.add_argument('--size', '-s', type=str, nargs='?', const=True, default=False,
                        help='Sort by Total_size_MB')
    parser.add_argument('--num', '-n', type=int, nargs='?', default=10,
                        help='Number of tables to display in output.', choices=range(1, 21))
    args = parser.parse_args()
    # begin compilation summary report
    print("{}Compiling database summary report...\n".format(Colors.fg.green),
          "Thank you for your patience.{}\n".format(Colors.reset))
    site = get_site_name()
    env = get_environment()
    db_name = get_dbname()
    table_prefix = get_table_prefix(env, site)
    core_version = get_core_version()
    db_size = get_dbsize()
    counts = build_count_dictionary()
    print_header()
    print_optimization_variables(counts)
    # will only print table listing if given storage engine is used.
    # set sorter
    if args.size:
        sortby = "Total_size_MB"
    else:
        sortby = "Rows"
    tblnum = args.num
    if int(counts['myisam']) > 0:
        print_tables("MyISAM", sortby, tblnum)
    else:
        pass
    if int(counts['innodb']) > 0:
        print_tables("InnoDB", sortby, tblnum)
    else:
        pass
    print("\n{}This is the end of the {}dbsummary{} report.".format(
          Colors.fg.cyan, Colors.fg.yellow, Colors.fg.cyan))

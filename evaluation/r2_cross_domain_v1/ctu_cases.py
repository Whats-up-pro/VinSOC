"""New evaluator-only CTU questions; no controller/prompt mappings live here.

These expand the already developed S5/S7 schema. They are not unseen-schema or
independent holdout observations. Families disclose repeated SQL structures.
"""
import hashlib
import json

from sqlglot import exp, parse_one


def _family(sql):
    tree = parse_one(sql, read="duckdb")
    for literal in list(tree.find_all(exp.Literal)):
        literal.replace(exp.Literal.string("<string>" if literal.is_string else "<number>"))
    return hashlib.sha256(tree.sql(dialect="duckdb").encode()).hexdigest()


def new_ctu_cases():
    s5, s7 = "source_dataset='ctu13_s5'", "source_dataset='ctu13_s7'"
    f = "network_flows"
    rows = []

    def add(split, difficulty, question, query, features=()):
        identity = json.dumps({"database_id": "ctu_dev", "question": question, "sql": query}, sort_keys=True)
        rows.append({"case_id": "ctu_cross_" + hashlib.sha256(identity.encode()).hexdigest()[:16],
                     "database_id": "ctu_dev", "question": question, "gold_sql": query,
                     "difficulty": difficulty, "features": list(features), "family_id": _family(query),
                     "split": split, "domain": "network_telemetry", "benchmark_locked": False,
                     "comparator": "ordered_rows" if parse_one(query, read="duckdb").args.get("order") else "unordered_multiset"})

    basic = [
        ("List source and destination IPs of RSVP flows in CTU scenario 5.", f"SELECT src_ip,dst_ip FROM {f} WHERE {s5} AND protocol='RSVP'"),
        ("List event time, source IP and destination IP of ARP flows in CTU scenario 7 with a missing destination port.", f"SELECT event_time,src_ip,dst_ip FROM {f} WHERE {s7} AND protocol='ARP' AND dst_port IS NULL"),
        ("List source row ID and label of PIM flows in CTU scenario 5.", f"SELECT source_row_id,label FROM {f} WHERE {s5} AND protocol='PIM'"),
        ("List source IP and outbound bytes of ICMP flows in CTU scenario 5 whose outbound bytes exceed 1000.", f"SELECT src_ip,bytes_out FROM {f} WHERE {s5} AND protocol='ICMP' AND bytes_out>1000"),
        ("List destination IP and destination port of RTCP flows in CTU scenario 7 with zero outbound bytes.", f"SELECT dst_ip,dst_port FROM {f} WHERE {s7} AND protocol='RTCP' AND bytes_out=0"),
        ("List event time and action of RTP flows in CTU scenario 5 at or after 2011-08-15 17:00:00.", f"SELECT event_time,action FROM {f} WHERE {s5} AND protocol='RTP' AND event_time>=TIMESTAMP '2011-08-15 17:00:00'"),
        ("List source IP, source port and destination IP of IGMP flows in CTU scenario 7 with a missing source port.", f"SELECT src_ip,src_port,dst_ip FROM {f} WHERE {s7} AND protocol='IGMP' AND src_port IS NULL"),
        ("List source IP, destination IP and protocol of CTU scenario 7 flows with over 1000000 outbound bytes and zero inbound bytes.", f"SELECT src_ip,dst_ip,protocol FROM {f} WHERE {s7} AND bytes_out>1000000 AND bytes_in=0"),
    ]
    for question, sql in basic:
        add("evaluation", "basic", question, sql)
    medium = [
        ("Count distinct source/destination IP pairs for UDP in CTU scenario 5, retaining NULL-containing pairs according to DuckDB tuple DISTINCT semantics.", f"SELECT COUNT(DISTINCT (src_ip,dst_ip)) FROM {f} WHERE {s5} AND protocol='UDP'", ("distinct", "null")),
        ("How many distinct destination ports occur in TCP flows in CTU scenario 7?", f"SELECT COUNT(DISTINCT dst_port) FROM {f} WHERE {s7} AND protocol='TCP'", ("distinct",)),
        ("How many distinct source ports occur in UDP flows in CTU scenario 5?", f"SELECT COUNT(DISTINCT src_port) FROM {f} WHERE {s5} AND protocol='UDP'", ("distinct",)),
        ("List distinct protocol/action pairs in CTU scenario 7.", f"SELECT DISTINCT protocol,action FROM {f} WHERE {s7}", ("distinct",)),
        ("List distinct source IP/label pairs in CTU scenario 5 whose label begins with flow=From-Botnet.", f"SELECT DISTINCT src_ip,label FROM {f} WHERE {s5} AND starts_with(label,'flow=From-Botnet')", ("distinct", "prefix")),
        ("List distinct destination IPs in CTU scenario 7 whose label begins with flow=From-Normal.", f"SELECT DISTINCT dst_ip FROM {f} WHERE {s7} AND starts_with(label,'flow=From-Normal')", ("distinct", "prefix")),
        ("For each source dataset, return its number of distinct source IPs, ordered by source dataset.", f"SELECT source_dataset,COUNT(DISTINCT src_ip) FROM {f} GROUP BY source_dataset ORDER BY source_dataset", ("distinct", "group_having", "order_limit")),
        ("How many distinct labels occur in CTU scenario 5?", f"SELECT COUNT(DISTINCT label) FROM {f} WHERE {s5}", ("distinct",)),
        ("For each protocol in CTU scenario 5, return the flow count and minimum/maximum outbound bytes, ordered by protocol.", f"SELECT protocol,COUNT(*),MIN(bytes_out),MAX(bytes_out) FROM {f} WHERE {s5} GROUP BY protocol ORDER BY protocol", ("group_having", "order_limit")),
        ("For each source dataset and protocol, return total outbound bytes and average inbound bytes, ordered by source dataset then protocol.", f"SELECT source_dataset,protocol,SUM(bytes_out),AVG(bytes_in) FROM {f} GROUP BY source_dataset,protocol ORDER BY source_dataset,protocol", ("group_having", "order_limit")),
        ("Return the three most frequent UDP destination IPs in CTU scenario 7 with their flow counts; break count ties by destination IP ascending.", f"SELECT dst_ip,COUNT(*) AS n FROM {f} WHERE {s7} AND protocol='UDP' GROUP BY dst_ip ORDER BY n DESC,dst_ip ASC LIMIT 3", ("group_having", "order_limit")),
        ("Return the seven most frequent TCP destination ports at most 1024 in CTU scenario 5 with counts; break count ties by port ascending.", f"SELECT dst_port,COUNT(*) AS n FROM {f} WHERE {s5} AND protocol='TCP' AND dst_port<=1024 GROUP BY dst_port ORDER BY n DESC,dst_port ASC LIMIT 7", ("group_having", "order_limit")),
        ("For each calendar date in CTU scenario 5, count flows with a label beginning flow=From-Botnet; order dates ascending.", f"SELECT CAST(event_time AS DATE) AS day,COUNT(*) FROM {f} WHERE {s5} AND starts_with(label,'flow=From-Botnet') GROUP BY CAST(event_time AS DATE) ORDER BY day", ("group_having", "order_limit", "time")),
        ("List labels with at least 100 flows in CTU scenario 7 with their counts, ordered by label.", f"SELECT label,COUNT(*) FROM {f} WHERE {s7} GROUP BY label HAVING COUNT(*)>=100 ORDER BY label", ("group_having", "order_limit")),
        ("Return the two source IPs with highest total outbound bytes in CTU scenario 5 and their totals; break total ties by source IP ascending.", f"SELECT src_ip,SUM(bytes_out) AS total FROM {f} WHERE {s5} GROUP BY src_ip ORDER BY total DESC,src_ip ASC LIMIT 2", ("group_having", "order_limit")),
        ("For each protocol in CTU scenario 7, count flows with both byte fields NULL; order protocols ascending.", f"SELECT protocol,SUM(CASE WHEN bytes_out IS NULL AND bytes_in IS NULL THEN 1 ELSE 0 END) FROM {f} WHERE {s7} GROUP BY protocol ORDER BY protocol", ("group_having", "order_limit", "null")),
    ]
    for question, sql, features in medium:
        add("evaluation", "medium", question, sql, features)
    advanced = [
        ("Count CTU scenario 5 flows whose outbound bytes exceed the average outbound bytes of scenario 5.", f"SELECT COUNT(*) FROM {f} WHERE {s5} AND bytes_out>(SELECT AVG(bytes_out) FROM {f} WHERE {s5})", ("nested",)),
        ("List protocols in CTU scenario 7 whose average outbound bytes exceed the average across all scenario 7 flows; order protocols ascending.", f"SELECT protocol FROM {f} WHERE {s7} GROUP BY protocol HAVING AVG(bytes_out)>(SELECT AVG(bytes_out) FROM {f} WHERE {s7}) ORDER BY protocol", ("nested", "group_having", "order_limit")),
        ("List source IPs observed in both CTU scenario 5 and scenario 7, without duplicates.", f"SELECT src_ip FROM {f} WHERE {s5} INTERSECT SELECT src_ip FROM {f} WHERE {s7}", ("nested", "distinct")),
        ("List UDP destination IPs present in CTU scenario 5 but absent from UDP in scenario 7, without duplicates.", f"SELECT dst_ip FROM {f} WHERE {s5} AND protocol='UDP' EXCEPT SELECT dst_ip FROM {f} WHERE {s7} AND protocol='UDP'", ("nested", "distinct")),
        ("Count the latest flow per source IP in CTU scenario 7, selecting by event time descending then source row ID descending within each source IP.", f"WITH ranked AS (SELECT ROW_NUMBER() OVER(PARTITION BY src_ip ORDER BY event_time DESC,source_row_id DESC) AS rn FROM {f} WHERE {s7}) SELECT COUNT(*) FROM ranked WHERE rn=1", ("nested", "order_limit", "window")),
        ("For each source dataset, return the fraction of all flows whose label begins with flow=From-Botnet; include all labels in the denominator and order datasets ascending.", f"WITH totals AS (SELECT source_dataset,COUNT(*) AS n,SUM(CASE WHEN starts_with(label,'flow=From-Botnet') THEN 1 ELSE 0 END) AS bot FROM {f} GROUP BY source_dataset) SELECT source_dataset,bot*1.0/NULLIF(n,0) FROM totals ORDER BY source_dataset", ("nested", "group_having", "prefix", "order_limit")),
        ("Count distinct destination IPs receiving TCP flows after 2011-08-15 17:00:00 in CTU scenario 5 and after 2011-08-16 14:00:00 in scenario 7; use strict time boundaries.", f"SELECT COUNT(*) FROM (SELECT dst_ip FROM {f} WHERE {s5} AND protocol='TCP' AND event_time>TIMESTAMP '2011-08-15 17:00:00' INTERSECT SELECT dst_ip FROM {f} WHERE {s7} AND protocol='TCP' AND event_time>TIMESTAMP '2011-08-16 14:00:00') AS shared", ("nested", "distinct", "time")),
        ("Return dataset/protocol flow counts exceeding that dataset's average protocol-group count; order by dataset then protocol.", f"WITH groups AS (SELECT source_dataset,protocol,COUNT(*) AS n FROM {f} GROUP BY source_dataset,protocol) SELECT g.source_dataset,g.protocol,g.n FROM groups g WHERE g.n>(SELECT AVG(other.n) FROM groups other WHERE other.source_dataset=g.source_dataset) ORDER BY g.source_dataset,g.protocol", ("nested", "group_having", "order_limit")),
    ]
    for question, sql, features in advanced:
        add("evaluation", "advanced", question, sql, features)
    calibration = [
        ("Return minimum and maximum event time for each source dataset, ordered by dataset.", f"SELECT source_dataset,MIN(event_time),MAX(event_time) FROM {f} GROUP BY source_dataset ORDER BY source_dataset", ("group_having", "time", "order_limit")),
        ("Return total outbound plus inbound bytes by protocol in CTU scenario 5, treating missing inbound bytes as zero; order by protocol.", f"SELECT protocol,SUM(bytes_out+COALESCE(bytes_in,0)) FROM {f} WHERE {s5} GROUP BY protocol ORDER BY protocol", ("group_having", "null", "order_limit")),
        ("Count flows with missing destination port by protocol in CTU scenario 7, ordered by protocol.", f"SELECT protocol,COUNT(*) FROM {f} WHERE {s7} AND dst_port IS NULL GROUP BY protocol ORDER BY protocol", ("group_having", "null", "order_limit")),
        ("Return the event time span in seconds for each source dataset, ordered by dataset.", f"SELECT source_dataset,DATE_DIFF('second',MIN(event_time),MAX(event_time)) FROM {f} GROUP BY source_dataset ORDER BY source_dataset", ("group_having", "time", "order_limit")),
        ("Count flows with a missing source port and label beginning flow=From-Normal for each source dataset, ordered by dataset.", f"SELECT source_dataset,COUNT(*) FROM {f} WHERE src_port IS NULL AND starts_with(label,'flow=From-Normal') GROUP BY source_dataset ORDER BY source_dataset", ("group_having", "null", "prefix", "order_limit")),
        ("Return the four most frequent labels in CTU scenario 5 with counts; break count ties by label ascending.", f"SELECT label,COUNT(*) AS n FROM {f} WHERE {s5} GROUP BY label ORDER BY n DESC,label ASC LIMIT 4", ("group_having", "order_limit")),
        ("For each source dataset, return the fraction of flows with zero outbound bytes; include NULL byte values in the flow denominator and order by dataset.", f"SELECT source_dataset,SUM(CASE WHEN bytes_out=0 THEN 1 ELSE 0 END)*1.0/COUNT(*) FROM {f} GROUP BY source_dataset ORDER BY source_dataset", ("group_having", "null", "order_limit")),
        ("Count distinct source/destination IP pairs in CTU scenario 7, retaining NULL-containing pairs according to DuckDB tuple DISTINCT semantics.", f"SELECT COUNT(DISTINCT (src_ip,dst_ip)) FROM {f} WHERE {s7}", ("distinct", "null")),
    ]
    for question, sql, features in calibration:
        add("calibration", "medium", question, sql, features)
    return rows

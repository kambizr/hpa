#! /bin/bash
java -cp /etc/hbase/conf.hbasev3:/etc/hadoop/conf.hadoopv3:./ToolBox-assembly-0.1.0-SNAPSHOT.jar tools.manifestTool -i | tee  before_activity

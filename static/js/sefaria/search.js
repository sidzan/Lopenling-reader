const $ = require('./sefariaJquery');
const extend            = require('extend');
const FilterNode = require('./FilterNode');
const SearchState = require('./searchState');


class HackyQueryAborter{
    /*Used to abort multiple ajax queries. Stand-in until AbortController is no longer experimental. At that point
    * we'll want to replace our ajax queries with fetch*/
    constructor() {
        this._queryList = [];
    }
    addQuery(ajaxQuery) {
        this._queryList.push(ajaxQuery);
    }
    abort() {
        this._queryList.map(ajaxQuery => ajaxQuery.abort());
    }
}


class Search {
    constructor(searchIndexText, searchIndexSheet) {
      this.searchIndexText = searchIndexText;
      this.searchIndexSheet = searchIndexSheet;
      this._cache = {};
      this.sefariaQueryQueue = {hits: {hits:[], total: 0, max_score: 0.0}, lastSeen: -1};
      this.dictaQueryQueue = {lastSeen: -1, hits: {total: 0, hits:[]}};
      this.queryDictaFlag = true;
      this.dictaCounts = null;
      this.sefariaSheetsResult = null;
      this.buckets = [];
      this.queryAborter = new HackyQueryAborter();
      // this.dictaSearchUrl = 'http://34.206.201.228';
      this.dictaSearchUrl = 'https://sefaria.loadbalancer.dicta.org.il';
    }
    cache(key, result) {
        if (result !== undefined) {
           this._cache[key] = result;
        }
        return this._cache[key];
    }
    sefariaQuery(args, isQueryStart, wrapper) {
        return new Promise((resolve, reject) => {
            let req = JSON.stringify(this.get_query_object(args));
            wrapper.addQuery($.ajax({
                url: `${Sefaria.apiHost}/api/search-wrapper`,
                type: 'POST',
                data: req,
                contentType: "application/json; charset=utf-8",
                crossDomain: true,
                processData: false,
                dataType: 'json',
                success: data => resolve(data),
                error: reject
            }));
        }).then(x => {
            if (args.type === "sheet") {
                this.sefariaSheetsResult = x;
                return null;
            }
            for (let i=0; i < x.hits.hits.length; i++) {
                x.hits.hits[i]['comp_date'] = x.hits.hits[i]._source.comp_date;
                x.hits.hits[i]['cameFrom'] = 'Sefaria';
                x.hits.hits[i]['score'] =  x.hits.hits[i]['_score'] * -1;
            }

            let mergedHits = this.sefariaQueryQueue.hits.hits.concat(x.hits.hits);
            let lastSeen = this.sefariaQueryQueue.lastSeen + x.hits.hits.length;
            this.sefariaQueryQueue = x;
            this.sefariaQueryQueue.hits.hits = mergedHits;
            this.sefariaQueryQueue.lastSeen = lastSeen;
        });

    }
    dictaQuery(args, isQueryStart, wrapper) {
        function ammendArgsForDicta(standardArgs, lastSeen) {
            let filters = (standardArgs.applied_filters) ? standardArgs.applied_filters.map(book => {
                book = book.replace(/\//g, '.');
                return book.replace(/ /g, '_');
            }) : false;
            return {
                query: standardArgs.query,
                from: ('start' in standardArgs) ? lastSeen + 1 : 0,
                size: standardArgs.size,
                limitedToBooks: filters,
                sort: (standardArgs.sort_type === "relevance") ? 'pagerank' : 'corpus_order_path',
                smallUnitsOnly: true
            };
        }
        return new Promise((resolve, reject) => {
            
            if (this.queryDictaFlag && args.type === "text") {
                if (this.dictaQueryQueue.lastSeen + 1 >= this.dictaQueryQueue.hits.total && ('start' in args && args['start'] > 0)) {
                    /* don't make new queries if results are exhausted.
                     * 'start' is omitted on first query (defaults to 0). On a first query, we'll always want to query.
                     */
                    resolve({total: this.dictaQueryQueue.hits.total, hits: []});
                }
                else {
                    wrapper.addQuery($.ajax({
                        url: `${this.dictaSearchUrl}/search`,
                        type: 'POST',
                        dataType: 'json',
                        contentType: 'application/json; charset=UTF-8',
                        data: JSON.stringify(ammendArgsForDicta(args, this.dictaQueryQueue.lastSeen)),
                        success: data => resolve(data),
                        error: reject
                    }));
                }

            }
            else {
                resolve({total: 0, hits: []});
            }
        }).then(x => {
            let adaptedHits = [];
            x.hits.forEach(hit => {
                const bookData = hit.xmlId.split(".");
                const categories = bookData.slice(0, 2);
                const bookTitle = bookData[2].replace(/_/g, ' ');
                const bookLoc = bookData.slice(3, 5).join(':');
                const version = "Tanach with Ta'amei Hamikra";
                adaptedHits.push({
                    _source: {
                        type: 'text',
                        lang: "he",
                        version: version,
                        path: categories,
                        ref: `${bookTitle} ${bookLoc}`,
                        heRef: hit.hebrewPath,
                        pagesheetrank: (hit.pagerank) ? hit.pagerank : 0,
                    },
                    highlight: {naive_lemmatizer: [hit.highlight[0].text]},
                    score: (hit.pagerank) ? hit.pagerank * -1 : 0,
                    comp_date: -10000 + adaptedHits.length,
                    _id: `${bookTitle} ${bookLoc} (${version} [he])`,
                    cameFrom: 'dicta'

                });
            });
            this.dictaQueryQueue = {
                hits: {
                    total: x.total,
                    hits: adaptedHits
                },
                lastSeen: ('start' in args) ? this.dictaQueryQueue.lastSeen + adaptedHits.length : adaptedHits.length

            }
        }).catch(x => {
            console.log(x)
        });
    }
    dictaBooksQuery(args, wrapper) {
        return new Promise((resolve, reject) => {
            if (this.dictaCounts === null && args.type === "text") {
                if (this.queryDictaFlag) {
                    wrapper.addQuery($.ajax({
                        url: `${this.dictaSearchUrl}/books`,
                        type: 'POST',
                        dataType: 'json',
                        contentType: "application/json;charset=UTF-8",
                        data: JSON.stringify({query: args.query, smallUnitsOnly: true}),
                        timeout: 3000,
                        success: data => resolve(data),
                        error: reject
                    }));
                }
                else {
                    resolve([]);
                }
            }
            else {
                resolve(null);
            }
        }).then(x => {
            if(x === null)
                return;
            let buckets = [];
            x.forEach(bucket => {
               buckets.push({
                   key: bucket['englishBookName'].map(i => i.replace(/_/g, " ")).join('/'),
                   doc_count: bucket['count']
               });
            });
            this.dictaCounts = buckets;
        }, x => {
            this.queryDictaFlag = false;
            console.log(x);
        });
    }
    isDictaQuery(args) {
        return RegExp(/^[^a-zA-Z]*$/).test(args.query); // If English appears in query, search in Sefaria only
    }
    getPivot(queue, minValue, sortType) {

        // if this is the last query, this will be the last chance to return results
        if (this.dictaQueryQueue.lastSeen + 1 >= this.dictaQueryQueue.hits.total &&
            this.sefariaQueryQueue.lastSeen + 1 >= this.sefariaQueryQueue.hits.total)
            return queue.length;

        // return whole queue if the last item in queue is equal to minValue

        if (Math.abs(queue[queue.length - 1][sortType] - minValue) <= 0.001 ) // float comparison
            return queue.length;

        const pivot = queue.findIndex(x => x[sortType] > minValue);
        return (pivot >= 0) ? pivot : 0;
    }
    mergeQueries(addAggregations, sortType, filters) {
        // function getPivot(queue, minValue, lastSeen, total) {
        //     if (lastSeen + 1 >= total)
        //         return queue.length;
        //     let pivot = queue.findIndex(x => x[sortType] > minValue);
        //     return (pivot >= 0) ? pivot : queue.length  //lastIndex returns -1 if value is not found -> then return the entire list
        // }
        let result = {hits: {}};
        if(addAggregations) {

            let newBuckets = this.sefariaQueryQueue['aggregations']['path']['buckets'].filter(
                x => !(RegExp(/^Tanakh\//).test(x.key)));
            newBuckets = newBuckets.concat(this.dictaCounts);
            result.aggregations = {path: {buckets: newBuckets}};
            this.buckets = newBuckets;
        }
        if (!!filters.length) {
            const expression = new RegExp(`^(${filters.join('|')})(\/.*|$)`);
            result.hits.total = this.buckets.reduce((total, currentBook) => {
                if (expression.test(currentBook.key)) {
                    total += currentBook.doc_count;
                }
                return total
            }, 0);
        }
        else {
            result.hits.total = this.sefariaQueryQueue.hits.total + this.dictaQueryQueue.hits.total;
        }

        let sefariaHits = (this.queryDictaFlag)
            ? this.sefariaQueryQueue.hits.hits.filter(i => !(i._source.categories.includes("Tanakh")))
            : this.sefariaQueryQueue.hits.hits;
        let dictaHits = this.dictaQueryQueue.hits.hits;

        let finalHits;
        if (!(dictaHits.length) || !(sefariaHits.length)) /* either or both queues are empty */ {
            finalHits = dictaHits.concat(sefariaHits).sort((i, j) => i[sortType] - j[sortType]);
            this.sefariaQueryQueue.hits.hits = [];
            this.dictaQueryQueue.hits.hits = [];
        }
        else {
            // when sorting by relevance adjust Dicta score's mean and standard deviation to match Sefaria's
            if (sortType === "score"){
                let sefariaMeanScore = sefariaHits.reduce(
                    (total, nextValue) => total + nextValue.score / sefariaHits.length, 0
                );
                let dictaMeanScore = dictaHits.reduce(
                    (total, nextValue) => total + nextValue.score / sefariaHits.length, 0
                );

                let sefariaStd = Math.sqrt(sefariaHits.reduce(
                    (total, nextValue) => total + Math.pow(nextValue.score - sefariaMeanScore, 2), 0
                ));
                let dictaStd = Math.sqrt(dictaHits.reduce(
                    (total, nextValue) => total + Math.pow(nextValue.score - dictaMeanScore, 2), 0
                ));

                let factor = (dictaStd !== 0) ?sefariaStd/dictaStd : 1;
                for (let i=0; i<dictaHits.length; i++) {
                    dictaHits[i].score = dictaHits[i].score * factor;
                }

                dictaMeanScore = dictaHits.reduce(
                    (total, nextValue) => total + nextValue.score / sefariaHits.length, 0
                );
                let delta = sefariaMeanScore - dictaMeanScore;
                for (let i=0; i < dictaHits.length; i++) {
                    dictaHits[i].score = dictaHits[i].score + delta;
                }
            }

            const lastScore = Math.min(sefariaHits[sefariaHits.length-1][sortType], dictaHits[dictaHits.length-1][sortType]);
            //const sefariaPivot = getPivot(sefariaHits, lastScore, this.sefariaQueryQueue.lastSeen, this.sefariaQueryQueue.hits.total);
            //const dictaPivot = getPivot(dictaHits, lastScore, this.dictaQueryQueue.lastSeen, this.dictaQueryQueue.hits.total);
            const sefariaPivot = this.getPivot(sefariaHits, lastScore, sortType);
            const dictaPivot = this.getPivot(dictaHits, lastScore, sortType);

            this.sefariaQueryQueue.hits.hits = sefariaHits.slice(sefariaPivot);
            sefariaHits = sefariaHits.slice(0, sefariaPivot);
            this.dictaQueryQueue.hits.hits = dictaHits.slice(dictaPivot);
            dictaHits = dictaHits.slice(0, dictaPivot);
            finalHits = dictaHits.concat(sefariaHits).sort((i, j) => i[sortType] - j[sortType]);
        }
        // if (sortType !== "score")
        //     finalHits.reverse();
        result.hits.hits = finalHits;
        return result;

        // if(this.queryDictaFlag) {
        //     this.sefariaQueryQueue.hits.total += this.dictaQueryQueue.hits.total;
        //
        //     let sefariaHits = this.sefariaQueryQueue.hits.hits.filter(x => !("Tanakh" in x._source.categories));
        // else {
        //         sefariaHits = this.sefariaQueryQueue.hits.hits;
        //      }
        //     // newHits = this.dictaQueryQueue.hits.hits.concat(newHits);
        //     // this.sefariaQueryQueue.hits.hits = newHits;
        // }
    }
    execute_query(args) {
        // To replace sjs.search.post in search.js

        /* args can contain
         query: query string
         size: size of result set
         start: from what result to start
         type: "sheet" or "text"
         applied_filters: filter query by these filters
         appliedFilterAggTypes: array of same len as applied_filters giving aggType for each filter
         field: field to query in elastic_search
         sort_type: See SearchState.metadataByType for possible sort types
         exact: if query is exact
         success: callback on success
         error: callback on error
         */
        if (!args.query) {
            return;
        }

        let isQueryStart = !(args.start);
        if (isQueryStart) // don't touch these parameters if not a text search
        {
            if (args.type === 'text') {
                this.dictaCounts = null;
                this.queryDictaFlag = this.isDictaQuery(args);
                this.sefariaQueryQueue = {hits: {hits: [], total: 0, max_score: 0.0}, lastSeen: -1};
                this.dictaQueryQueue = {lastSeen: -1, hits: {total: 0, hits: []}};
                this.queryAborter.abort();
            }
        }

        let req = JSON.stringify(this.get_query_object(args));
        let cache_result = this.cache(req);
        if (cache_result) {
            args.success(cache_result);
            return null;
        }
        let queryAborter = new HackyQueryAborter();
        this.queryAborter = queryAborter;
        /*
        return $.ajax({
            url: `${Sefaria.apiHost}/api/search-wrapper`,
            type: 'POST',
            data: req,
            contentType: "application/json; charset=utf-8",
            crossDomain: true,
            processData: false,
            dataType: 'json',
            success: function(data) {
                this.cache(req, data);
                args.success(data);
            }.bind(this),
            error: args.error
        });
         */
        // const sortType = (args.)
        const updateAggreagations = (args.aggregationsToUpdate.length > 0);
        if (this.queryDictaFlag) {
            Promise.all([
            this.sefariaQuery(args, updateAggreagations, queryAborter),
            this.dictaQuery(args, updateAggreagations, queryAborter),
            this.dictaBooksQuery(args, queryAborter)
        ]).then(() => {
            if (args.type === "sheet") {
                args.success(this.sefariaSheetsResult);
            }
            else {
                const sortType = (args.sort_type === 'relevance') ? 'score' : 'comp_date';
                args.success(this.mergeQueries(updateAggreagations, sortType, args.applied_filters));
            }
        }).catch(x => console.log(x));
        // }).catch(args.error);
        }
        else {
            this.sefariaQuery(args, updateAggreagations, queryAborter)
                .then(() => {
                    if (args.type === "sheet")
                        args.success(this.sefariaSheetsResult);
                    else
                        args.success(this.sefariaQueryQueue);
                    })
        }

        return queryAborter;
    }
    get_query_object({
      query,
      applied_filters,
      appliedFilterAggTypes,
      aggregationsToUpdate,
      size,
      start,
      type,
      field,
      sort_type,
      exact
    }) {
      const { sortTypeArray, aggregation_field_array } = SearchState.metadataByType[type];
      const { sort_method, fieldArray, score_missing, direction } = sortTypeArray.find( x => x.type === sort_type );
      return {
        type,
        query,
        field,
        source_proj: true,
        slop: exact ? 0 : 10,
        start,
        size,
        filters: applied_filters.length ? applied_filters : [],
        filter_fields: appliedFilterAggTypes,
        aggs: aggregationsToUpdate,
        sort_method,
        sort_fields: fieldArray,
        sort_reverse: direction === "desc",
        sort_score_missing: score_missing,
      };
    }

    process_text_hits(hits) {
      var newHits = [];
      var newHitsObj = {};  // map ref -> index in newHits
      for (var i = 0; i < hits.length; i++) {
        let currRef = hits[i]._source.ref;
        let newHitsIndex = newHitsObj[currRef];
        if (typeof newHitsIndex != "undefined") {
          newHits[newHitsIndex].duplicates = newHits[newHitsIndex].duplicates || [];
          newHits[newHitsIndex].insertInOrder(hits[i], (a, b) => a._source.version_priority - b._source.version_priority);
        } else {
          newHits.push([hits[i]]);
          newHitsObj[currRef] = newHits.length - 1;
        }
      }
      newHits = newHits.map(hit_list => {
        let hit = hit_list[0];
        if (hit_list.length > 1) {
          hit.duplicates = hit_list.slice(1);
        }
        return hit;
      });
      return newHits;
    }
    buildFilterTree(aggregation_buckets, appliedFilters) {
      //returns object w/ keys 'availableFilters', 'registry'
      //Add already applied filters w/ empty doc count?
      var rawTree = {};

      appliedFilters.forEach(
          fkey => this._addAvailableFilter(rawTree, fkey, {"docCount":0})
      );

      aggregation_buckets.forEach(
          f => this._addAvailableFilter(rawTree, f["key"], {"docCount":f["doc_count"]})
      );
      this._aggregate(rawTree);
      return this._build(rawTree);
    }
    _addAvailableFilter(rawTree, key, data) {
      //key is a '/' separated key list, data is an arbitrary object
      //Based on http://stackoverflow.com/a/11433067/213042
      var keys = key.split("/");
      var base = rawTree;

      // If a value is given, remove the last name and keep it for later:
      var lastName = arguments.length === 3 ? keys.pop() : false;

      // Walk the hierarchy, creating new objects where needed.
      // If the lastName was removed, then the last object is not set yet:
      var i;
      for(i = 0; i < keys.length; i++ ) {
          base = base[ keys[i] ] = base[ keys[i] ] || {};
      }

      // If a value was given, set it to the last name:
      if( lastName ) {
          base = base[ lastName ] = data;
      }

      // Could return the last object in the hierarchy.
      // return base;
    }
    _aggregate(rawTree) {
      //Iterates the raw tree to aggregate doc_counts from the bottom up
      //Nod to http://stackoverflow.com/a/17546800/213042
      walker("", rawTree);
      function walker(key, branch) {
          if (branch !== null && typeof branch === "object") {
              // Recurse into children
              $.each(branch, walker);
              // Do the summation with a hacked object 'reduce'
              if ((!("docCount" in branch)) || (branch["docCount"] === 0)) {
                  branch["docCount"] = Object.keys(branch).reduce(function (previous, key) {
                      if (typeof branch[key] === "object" && "docCount" in branch[key]) {
                          previous += branch[key].docCount;
                      }
                      return previous;
                  }, 0);
              }
          }
      }
    }

    _build(rawTree) {
      //returns dict w/ keys 'availableFilters', 'registry'
      //Aggregate counts, then sort rawTree into filter objects and add Hebrew using Sefaria.toc as reference
      //Nod to http://stackoverflow.com/a/17546800/213042
      var path = [];
      var filters = [];
      var registry = {};

      var commentaryNode = new FilterNode();


      for(var j = 0; j < Sefaria.search_toc.length; j++) {
          var b = walk.call(this, Sefaria.search_toc[j]);
          if (b) filters.push(b);

          // Remove after commentary refactor ?
          // If there is commentary on this node, add it as a sibling
          if (commentaryNode.hasChildren()) {
            var toc_branch = Sefaria.toc[j];
            var cat = toc_branch["category"];
            // Append commentary node to result filters, add a fresh one for the next round
            var docCount = 0;
            if (rawTree.Commentary && rawTree.Commentary[cat]) { docCount += rawTree.Commentary[cat].docCount; }
            if (rawTree.Commentary2 && rawTree.Commentary2[cat]) { docCount += rawTree.Commentary2[cat].docCount; }
            extend(commentaryNode, {
                "title": cat + " Commentary",
                "aggKey": "Commentary/" + cat,
                "heTitle": "מפרשי" + " " + toc_branch["heCategory"],
                "docCount": docCount
            });
            registry[commentaryNode.aggKey] = commentaryNode;
            filters.push(commentaryNode);
            commentaryNode = new FilterNode();
          }
      }

      return { availableFilters: filters, registry };

      function walk(branch, parentNode) {
          var node = new FilterNode();

          node["docCount"] = 0;

          if("category" in branch) { // Category node

            path.push(branch["category"]);  // Place this category at the *end* of the path
            extend(node, {
              "title": path.slice(-1)[0],
              "aggKey": path.join("/"),
              "heTitle": branch["heCategory"]
            });

            for(var j = 0; j < branch["contents"].length; j++) {
                var b = walk.call(this, branch["contents"][j], node);
                if (b) node.append(b);
            }
          }
          else if ("title" in branch) { // Text Node
              path.push(branch["title"]);
              extend(node, {
                 "title": path.slice(-1)[0],
                 "aggKey": path.join("/"),
                 "heTitle": branch["heTitle"]
              });
          }

          try {
              var rawNode = rawTree;
              var i;

              for (i = 0; i < path.length; i++) {
                //For TOC nodes that we don't have results for, we catch the exception below.
                rawNode = rawNode[path[i]];
              }
              node["docCount"] += rawNode.docCount;
              registry[node.aggKey] = node;
              path.pop();
              return node;
          }
          catch (e) {
            path.pop();
            return false;
          }
      }
    }

    applyFilters(registry, appliedFilters) {
      var orphans = [];  // todo: confirm behavior
      appliedFilters.forEach(aggKey => {
        var node = registry[aggKey];
        if (node) { node.setSelected(true); }
        else { orphans.push(aggKey); }
      });
      return orphans;
    }

    getAppliedSearchFilters(availableFilters) {
      let appliedFilters = [];
      let appliedFilterAggTypes = [];
      //results = results.concat(this.orphanFilters);
      for (let tempFilter of availableFilters) {
          const tempApplied = tempFilter.getAppliedFilters();
          const tempAppliedTypes = tempApplied.map( x => tempFilter.aggType );  // assume all child filters have the same type as their parent
          appliedFilters = appliedFilters.concat(tempApplied);
          appliedFilterAggTypes = appliedFilterAggTypes.concat(tempAppliedTypes);
      }
      return {
        appliedFilters,
        appliedFilterAggTypes,
      };
    }

    buildAndApplyTextFilters(aggregation_buckets, appliedFilters, appliedFilterAggTypes, aggType) {
      const { availableFilters, registry } = this.buildFilterTree(aggregation_buckets, appliedFilters);
      const orphans = this.applyFilters(registry, appliedFilters);
      return { availableFilters, registry, orphans };
    }

    buildAndApplySheetFilters(aggregation_buckets, appliedFilters, appliedFilterAggTypes, aggType) {
      const availableFilters = aggregation_buckets.map( b => {
        const isHeb = Sefaria.hebrew.isHebrew(b.key);
        const enTitle = isHeb ? '' : b.key;
        const heTitle = isHeb ? b.key : (aggType === 'group' || !Sefaria.terms[b.key] ? '' : Sefaria.terms[b.key].he);
        const aggKey = enTitle || heTitle;
        const filterInd = appliedFilters.indexOf(aggKey);
        const isSelected = filterInd !== -1 && appliedFilterAggTypes[filterInd] === aggType;
        return new FilterNode(
          {
            title: enTitle,
            heTitle,
            docCount: b.doc_count,
            aggKey,
            aggType,
            selected: isSelected ? 1 : 0
          }
        );
      });
      return { availableFilters, registry: {}, orphans: [] };
    }
}

module.exports = Search;

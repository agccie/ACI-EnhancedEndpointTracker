/**
 * generic table used by app that supports variable columns and configurable displays per row. Also,
 * allows for API based sortable values and paging.
 * requirement to change the dataset and formatting on demand.
 */

function gHeader(args) {
    var self = this;
    // make everything observable for simplicity
    self.name = ko.observable(("name" in args)? args.name : "" )
    self.sort_name = ko.observable(("sort_name" in args)? args.sort_name : "")
    self.title = ko.observable(("title" in args)? args.title : self.name())
    self.sortable = ko.observable(("sortable" in args)? args.sortable : true)
    self.sorted = ko.observable(("sorted" in args)? args.sorted : false)
    self.sort_direction = ko.observable(("sort_direction" in args)? args.sort_direction: "")
    self.width = ko.observable(("width" in args)? args.width:"")
    //list of gCtrl objects
    self.control = ko.observableArray(("control" in args)? args.control : [])

    self.get_sort_name = ko.computed(function(){
        if(self.sort_name().length>0){ return self.sort_name()}
        return self.name()
    })
    self.get_css = ko.computed(function(){
        if(self.sortable()){ return "sortable"}
        return ""
    })
    self.get_sort_css = ko.computed(function(){
        if(self.sortable() && self.sorted()){
            if(self.sort_direction()=="asc"){
                return "sort-indicator icon-chevron-down"
            }else{
                return "sort-indicator icon-chevron-up"
            }
        }
        return ""
    })
}

function gCtrl(args){
    var self = this
    self.click = ("click" in args)? args.click : function(data){}
    self.disabled = ko.observable(("disabled" in args)? args.disabled : false )
    self.icon = ko.observable(("icon" in args)? args.icon : "icon-check")
    self.icon_status = ko.observable(("status" in args)? args.status : "")
    self.balloon = ko.observable(("tip" in args)? args.tip : "click")
    self.balloon_pos = ko.observable(("balloon_pos" in args)? args.balloon_pos : "up")
    self.btn_status = ko.computed(function(){
        if(self.icon_status().length>0){
            return "btn--"+self.icon_status()
        }
        return ""
    })
}


function gRow(data){
    var self = this;
    self.data = data;

    //get value of data attribute
    self.get_attribute = function(attr){
        if(self.data.hasOwnProperty(attr)){
            if(ko.isObservable(self.data[attr])){
                return self.data[attr]()
            }else{
                return self.data[attr]
            }
        }
        return ""
    }
    // data object can have 'formatter' object and if attribute name in formatter than return that
    // value, else return raw text
    self.get_attribute_html = function(attr){
        var text = self.get_attribute(attr)
        if(self.data.hasOwnProperty("formatter")){
            return self.data.formatter(attr, text)
        }
        return text
    }
}

function gTable() {
    var self = this;
    self.isLoading = ko.observable(false)
    self.headers = ko.observableArray()
    self.rows = ko.observableArray()
    self.page = ko.observable(0)
    self.page_size = ko.observable(25)
    self.page_window = ko.observable(5)
    self.page_enabled = ko.observable(true)
    self.result_count = ko.observable(null)
    self.result_count_wrapped = ko.observable(null)
    self.refresh_enabled = ko.observable(true)
    self.back_enabled = ko.observable(false)
    self.back_location = ko.observable("")
    self.display_no_data = ko.observable(true)
    self.no_data_message = ko.observable("No data to display")
    self.title = ko.observable("")
    self.url = ko.observable("")
    self.url_params = ko.observableArray([])
    // triggered when get or refresh occurs and should return list of objects (used to create gRows)
    self.refresh_handler = null                 
    // custom refresh which needs to pull the new data and manually set self.rows 
    self.custom_refresh = null

    // re-init table to defaults
    self.init = function(){
        self.isLoading(false)
        self.headers([])
        self.rows([])
        self.page_enabled(true)
        self.page(0)
        self.page_window(5)
        self.result_count(null)         //set be refresh or assumed to be length of rows
        self.result_count_wrapped(null) //actual count before results are wrapped 
        self.refresh_enabled(true)
        self.back_enabled(false)
        self.back_location("")
        self.display_no_data(true)
        self.no_data_message("No data to display")
        self.title("")
        self.url("")
        self.url_params([])
        self.custom_refresh = null
        self.refresh_handler = null
    }

    // implied client side paging if custom refresh is set
    self._client_paging = function(){
        return (typeof self.custom_refresh === "function")
    }
    // if back is enabled, redirect to back_location
    self.go_back = function(){
        forward(self.back_location())
    }
    //when client side paging is occurring, filter data rows to just those on the current page
    //else return all rows 
    self.get_paged_rows = ko.computed(function(){
        if(self._client_paging()){
            if(self.page()>=0 && self.page_size()>=0){
                var start = (self.page())*self.page_size()
                var end = (self.page()+1)*self.page_size()
                return self.rows().slice(start, end)
            }
            return []
        } else {
            return self.rows()
        }
    })

    //get total number of results
    self.get_total_count = ko.computed(function(){
        if(self.result_count()==null){
            return self.rows().length
        }
        return self.result_count()
    })
    self.get_total_count_wrapped = ko.computed(function(){
        if(self.result_count_wrapped()==null){ return 0 }
        if(self.result_count_wrapped()<=self.get_total_count()){ return 0 }
        return self.result_count_wrapped()
    })
    //get total number of pages
    self.get_total_pages = ko.computed(function(){
        if(self.page_size()>0){
            return Math.ceil(self.get_total_count()/self.page_size())
        }
        return 0
    })
    //for provided page, return highlight css if in view
    self.get_page_css = function(p){
        if(p-1==self.page()){ return " label--indigo"; }
        return ""
    }
    //return a list of page numbers within sliding view window
    self.get_in_view_pages = ko.computed(function(){
        var ret = []
        var b = Math.floor((self.page_window()-1)/2)
        var c = self.page()+1
        var max = self.get_total_pages()
        var s = c-b
        var e = c+b
        if(s < 1 ){ e+= 1-s ; s =1 }
        if(e > max ){ s-= (e-max) ; e = max}
        if(s < 1 ) { s = 1 } 
        //console.log("pages:"+max+", page:"+c+",start:"+s+",end:"+e)
        for(var i=s; i<=e; i++){ret.push(i)}
        return ret
    })
    // change page via start/last or specific page number
    self.pager = function(op){
        //op can be first, last, or an integer page number
        var page=1
        switch(op){
            case "first":   page=1; 
                            break;
            case "last":    page=self.get_total_pages(); 
                            break;
            case "next":    page=self.page()+2; 
                            break;
            case "prev":    page=self.page()
                            break;
            default: page=parseInt(op)
        }
        if(isNaN(page)){ page = 1 }
        if(page < 1){ page = 1 }
        if(page > self.get_total_pages()) { page = self.get_total_pages() }
        self.page(page-1)
        if(!self._client_paging()){
            self.refresh_data()
        }
    }

    // when sortable header is clicked, update which column is sorted and refresh data
    self.toggle_sort = function(hdr){
        //ignore clicks on non-sortable columns
        if(!hdr.sortable()){ return }
        if(hdr.sorted()){
            //clicked column is already sorted. If asc then change to desc. If desc, then disable
            //sorting on this column
            if(hdr.sort_direction()=="asc"){
                hdr.sort_direction("desc")
            }
            else{
                //disable sorting for this column
                hdr.sort_direction("")
                hdr.sorted(false)
            }
        }
        else{
            //disable sorting on all other columns and enable asc sorting for this column
            self.headers().forEach(function(elem){
                elem.sorted(false)
                elem.sort_direction("")
            })
            hdr.sort_direction("asc")
            hdr.sorted(true)
        }
        self.refresh_data()
    }

    // refresh data with sorting and paging
    self.refresh_data = function(){
        if(self._client_paging()){
            self.rows([])
            return self.custom_refresh()
        }
        self.isLoading(true)
        self.rows([])
        var url = self.url()+"?page="+self.page()+"&page-size="+self.page_size()
        //find which column we are sorting on and sort direction
        for(var i=0; i<self.headers().length; i++){
            var h=self.headers()[i]
            if(h.sorted()){
                url+= "&sort="+h.get_sort_name()+"|"+(h.sort_direction()=="asc"?"asc":"desc")
                break
            }
        }
        json_get(url, function(data){
            self.isLoading(false);
            self.result_count(("count" in data) ? data.count : null)
            var rows = []
            if(typeof self.refresh_handler === "function"){
                var ret = self.refresh_handler(data)
                if(Array.isArray(ret)){
                    ret.forEach(function(elem){rows.push(new gRow(elem))})
                }
            } else if("objects" in data){
                data.objects.forEach(function(elem){
                    var keys = Object.keys(elem)
                    if(keys.length>0){
                        rows.push(new gRow(elem[keys[0]]))
                    }
                })
            }
            self.rows(rows)
        })
    }
}

